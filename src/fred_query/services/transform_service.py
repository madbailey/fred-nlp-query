from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from datetime import date, timedelta

from fred_query.schemas.analysis import HistoricalSeriesContext, ObservationPoint
from fred_query.schemas.chart import DateSpanAnnotation
from fred_query.schemas.intent import TransformType


@dataclass
class SingleSeriesTransformResult:
    observations: list[ObservationPoint] | None
    basis: str | None
    units: str
    applied_window: int | None = None
    compare_on_transformed_series: bool = False
    warnings: list[str] = field(default_factory=list)


class TransformService:
    """Deterministic transforms and derived metrics."""

    _DAILY_PERIODS_PER_YEAR = 252

    @staticmethod
    def choose_relationship_frequency(
        frequencies: list[str],
    ) -> tuple[str, str, int, str]:
        normalized = [value.strip().lower() for value in frequencies if value]
        if any("annual" in value or value == "a" for value in normalized):
            return "a", "Annual", 1, "years"
        if any("quarter" in value or value == "q" for value in normalized):
            return "q", "Quarterly", 4, "quarters"
        return "m", "Monthly", 12, "months"

    @staticmethod
    def periods_per_year_for_frequency(frequency: str | None) -> int:
        normalized = (frequency or "").strip().lower()
        if normalized in {"d", "daily"} or "daily" in normalized:
            return TransformService._DAILY_PERIODS_PER_YEAR
        if normalized in {"w", "weekly"} or "weekly" in normalized:
            return 52
        if normalized in {"bw", "biweekly"} or "biweekly" in normalized:
            return 26
        if "semiannual" in normalized or "semi-annual" in normalized:
            return 2
        if normalized in {"q", "quarterly"} or "quarter" in normalized:
            return 4
        if normalized in {"a", "annual", "annually"} or "annual" in normalized or "year" in normalized:
            return 1
        return 12

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month_index = (value.month - 1) + months
        year = value.year + (month_index // 12)
        month = (month_index % 12) + 1
        if month == 2:
            leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            max_day = 29 if leap_year else 28
        elif month in {4, 6, 9, 11}:
            max_day = 30
        else:
            max_day = 31
        return date(year, month, min(value.day, max_day))

    def subtract_periods(
        self,
        value: date,
        *,
        periods: int,
        frequency: str | None,
    ) -> date:
        if periods <= 0:
            return value

        normalized = (frequency or "").strip().lower()
        if normalized in {"d", "daily"} or "daily" in normalized:
            return value - timedelta(days=periods)
        if normalized in {"w", "weekly"} or "weekly" in normalized:
            return value - timedelta(days=periods * 7)
        if normalized in {"bw", "biweekly"} or "biweekly" in normalized:
            return value - timedelta(days=periods * 14)
        if "semiannual" in normalized or "semi-annual" in normalized:
            return self._add_months(value, -(periods * 6))
        if normalized in {"q", "quarterly"} or "quarter" in normalized:
            return self._add_months(value, -(periods * 3))
        if normalized in {"a", "annual", "annually"} or "annual" in normalized or "year" in normalized:
            try:
                return value.replace(year=value.year - periods)
            except ValueError:
                return value.replace(month=2, day=28, year=value.year - periods)
        return self._add_months(value, -periods)

    def default_window_for_transform(
        self,
        *,
        transform: TransformType,
        frequency: str | None,
    ) -> int | None:
        if transform not in (
            TransformType.ROLLING_AVERAGE,
            TransformType.ROLLING_STDDEV,
            TransformType.ROLLING_VOLATILITY,
        ):
            return None

        periods_per_year = self.periods_per_year_for_frequency(frequency)
        if periods_per_year >= self._DAILY_PERIODS_PER_YEAR:
            return 30
        if periods_per_year >= 52:
            return 13
        if periods_per_year >= 12:
            return 12
        if periods_per_year >= 4:
            return 4
        return 3

    def resolve_transform_window(
        self,
        *,
        transform: TransformType,
        frequency: str | None,
        requested_window: int | None,
    ) -> tuple[int | None, list[str]]:
        if requested_window is not None:
            return requested_window, []

        default_window = self.default_window_for_transform(transform=transform, frequency=frequency)
        if default_window is None:
            return None, []

        return (
            default_window,
            [f"Used a default {default_window}-observation rolling window because the query did not specify one."],
        )

    def transform_warmup_periods(
        self,
        *,
        transform: TransformType,
        periods_per_year: int,
        window: int | None,
    ) -> int:
        if transform == TransformType.PERIOD_OVER_PERIOD_PERCENT_CHANGE:
            return 1
        if transform == TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE:
            return max(1, periods_per_year)
        if transform in (TransformType.ROLLING_AVERAGE, TransformType.ROLLING_STDDEV):
            return max(0, (window or 0) - 1)
        if transform == TransformType.ROLLING_VOLATILITY:
            return max(1, window or 0)
        return 0

    @staticmethod
    def relationship_max_lag(periods_per_year: int) -> int:
        if periods_per_year >= 12:
            return 12
        if periods_per_year >= 4:
            return 4
        return 2

    @staticmethod
    def calculate_pct_change(
        observations: list[ObservationPoint],
        *,
        periods: int,
    ) -> list[ObservationPoint]:
        if periods <= 0 or len(observations) <= periods:
            return []

        transformed: list[ObservationPoint] = []
        for index in range(periods, len(observations)):
            previous = observations[index - periods]
            current = observations[index]
            if previous.value == 0:
                continue
            transformed.append(
                ObservationPoint(
                    date=current.date,
                    value=((current.value / previous.value) - 1.0) * 100.0,
                )
            )
        return transformed

    @staticmethod
    def cumulative_growth_series(observations: list[ObservationPoint]) -> list[ObservationPoint]:
        if not observations:
            return []

        first_value = observations[0].value
        if first_value == 0:
            return []

        return [
            ObservationPoint(
                date=point.date,
                value=((point.value / first_value) - 1.0) * 100.0,
            )
            for point in observations
        ]

    @staticmethod
    def rolling_average(observations: list[ObservationPoint], *, window: int) -> list[ObservationPoint]:
        if window <= 0 or len(observations) < window:
            return []

        transformed: list[ObservationPoint] = []
        for index in range(window - 1, len(observations)):
            current_window = observations[index - window + 1 : index + 1]
            transformed.append(
                ObservationPoint(
                    date=observations[index].date,
                    value=sum(point.value for point in current_window) / window,
                )
            )
        return transformed

    @staticmethod
    def rolling_stddev(
        observations: list[ObservationPoint],
        *,
        window: int,
    ) -> list[ObservationPoint]:
        if window < 2 or len(observations) < window:
            return []

        transformed: list[ObservationPoint] = []
        for index in range(window - 1, len(observations)):
            current_window = observations[index - window + 1 : index + 1]
            values = [point.value for point in current_window]
            mean = sum(values) / window
            variance = sum((value - mean) ** 2 for value in values) / (window - 1)
            transformed.append(
                ObservationPoint(
                    date=observations[index].date,
                    value=sqrt(variance),
                )
            )
        return transformed

    def rolling_volatility(
        self,
        observations: list[ObservationPoint],
        *,
        window: int,
        periods_per_year: int,
    ) -> list[ObservationPoint]:
        period_returns = self.calculate_pct_change(observations, periods=1)
        if not period_returns:
            return []

        rolling_stddev = self.rolling_stddev(period_returns, window=window)
        annualization_factor = sqrt(max(1, periods_per_year))
        return [
            ObservationPoint(
                date=point.date,
                value=point.value * annualization_factor,
            )
            for point in rolling_stddev
        ]

    @staticmethod
    def filter_observations_by_date(
        observations: list[ObservationPoint],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ObservationPoint]:
        return [
            point
            for point in observations
            if (start_date is None or point.date >= start_date)
            and (end_date is None or point.date <= end_date)
        ]

    def apply_single_series_transform(
        self,
        observations: list[ObservationPoint],
        *,
        transform: TransformType,
        units: str,
        frequency: str | None,
        window: int | None = None,
    ) -> SingleSeriesTransformResult:
        if transform == TransformType.LEVEL:
            return SingleSeriesTransformResult(observations=None, basis=None, units=units)

        if transform == TransformType.NORMALIZED_INDEX:
            return SingleSeriesTransformResult(
                observations=self.normalize_to_index(observations),
                basis="Normalized index",
                units="Index (Base = 100)",
            )

        if transform == TransformType.TOTAL_GROWTH:
            return SingleSeriesTransformResult(
                observations=self.cumulative_growth_series(observations),
                basis="Cumulative percent change from the first observation",
                units="Percent",
                compare_on_transformed_series=True,
            )

        periods_per_year = self.periods_per_year_for_frequency(frequency)

        if transform == TransformType.PERIOD_OVER_PERIOD_PERCENT_CHANGE:
            return SingleSeriesTransformResult(
                observations=self.calculate_pct_change(observations, periods=1),
                basis="Period-over-period percent change",
                units="Percent",
                compare_on_transformed_series=True,
            )

        if transform == TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE:
            return SingleSeriesTransformResult(
                observations=self.calculate_pct_change(observations, periods=max(1, periods_per_year)),
                basis="Year-over-year percent change",
                units="Percent",
                compare_on_transformed_series=True,
            )

        applied_window, warnings = self.resolve_transform_window(
            transform=transform,
            frequency=frequency,
            requested_window=window,
        )
        if applied_window is None:
            return SingleSeriesTransformResult(observations=None, basis=None, units=units)

        if transform == TransformType.ROLLING_AVERAGE:
            return SingleSeriesTransformResult(
                observations=self.rolling_average(observations, window=applied_window),
                basis=f"{applied_window}-observation rolling average",
                units=units,
                applied_window=applied_window,
                compare_on_transformed_series=True,
                warnings=warnings,
            )

        if transform == TransformType.ROLLING_STDDEV:
            return SingleSeriesTransformResult(
                observations=self.rolling_stddev(observations, window=applied_window),
                basis=f"{applied_window}-observation rolling standard deviation",
                units=units,
                applied_window=applied_window,
                compare_on_transformed_series=True,
                warnings=warnings,
            )

        if transform == TransformType.ROLLING_VOLATILITY:
            return SingleSeriesTransformResult(
                observations=self.rolling_volatility(
                    observations,
                    window=applied_window,
                    periods_per_year=periods_per_year,
                ),
                basis=f"{applied_window}-observation rolling annualized volatility",
                units="Percent",
                applied_window=applied_window,
                compare_on_transformed_series=True,
                warnings=warnings,
            )

        return SingleSeriesTransformResult(observations=None, basis=None, units=units)

    @staticmethod
    def should_use_level_relationship(title: str, units: str) -> bool:
        normalized_title = title.lower()
        normalized_units = units.lower()
        level_markers = ("percent", "rate", "basis points", "bps")
        return any(marker in normalized_units for marker in level_markers) or "yield" in normalized_title

    def build_relationship_basis(
        self,
        observations: list[ObservationPoint],
        *,
        title: str,
        units: str,
        frequency: str | None,
        periods_per_year: int,
        transform: TransformType = TransformType.LEVEL,
        normalization: bool = False,
        requested_window: int | None = None,
    ) -> tuple[list[ObservationPoint], str, str, int | None, list[str]]:
        effective_transform = TransformType.LEVEL if transform == TransformType.NORMALIZED_INDEX else transform
        normalize_chart = normalization or transform == TransformType.NORMALIZED_INDEX

        if effective_transform != TransformType.LEVEL:
            transform_result = self.apply_single_series_transform(
                observations,
                transform=effective_transform,
                units=units,
                frequency=frequency,
                window=requested_window,
            )
            return (
                transform_result.observations or [],
                transform_result.basis or effective_transform.value.replace("_", " "),
                transform_result.units,
                transform_result.applied_window,
                list(transform_result.warnings),
            )

        if normalize_chart:
            return self.normalize_to_index(observations), "Normalized index", "Index (Base = 100)", None, []

        if self.should_use_level_relationship(title, units):
            return observations, "Reported level", units, None, []

        if periods_per_year > 1:
            year_over_year = self.calculate_pct_change(observations, periods=periods_per_year)
            if len(year_over_year) >= max(8, periods_per_year):
                return year_over_year, "Year-over-year percent change", "Percent", None, []

        period_change = self.calculate_pct_change(observations, periods=1)
        if period_change:
            return period_change, "Period-over-period percent change", "Percent", None, []

        return observations, "Reported level", units, None, []

    @staticmethod
    def align_on_dates(
        first: list[ObservationPoint],
        second: list[ObservationPoint],
    ) -> tuple[list[ObservationPoint], list[ObservationPoint]]:
        first_by_date = {point.date: point for point in first}
        second_by_date = {point.date: point for point in second}
        common_dates = sorted(set(first_by_date).intersection(second_by_date))
        return (
            [first_by_date[current_date] for current_date in common_dates],
            [second_by_date[current_date] for current_date in common_dates],
        )

    @staticmethod
    def _pearson_from_values(first_values: list[float], second_values: list[float]) -> float | None:
        if len(first_values) != len(second_values) or len(first_values) < 2:
            return None

        first_mean = sum(first_values) / len(first_values)
        second_mean = sum(second_values) / len(second_values)
        covariance = sum(
            (first_value - first_mean) * (second_value - second_mean)
            for first_value, second_value in zip(first_values, second_values, strict=True)
        )
        first_variance = sum((value - first_mean) ** 2 for value in first_values)
        second_variance = sum((value - second_mean) ** 2 for value in second_values)
        denominator = sqrt(first_variance * second_variance)
        if denominator == 0:
            return None
        return covariance / denominator

    def calculate_correlation(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
    ) -> float | None:
        if len(first) != len(second):
            raise ValueError("Correlation requires aligned observation lists.")
        return self._pearson_from_values(
            [point.value for point in first],
            [point.value for point in second],
        )

    def calculate_regression_slope(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
    ) -> float | None:
        if len(first) != len(second) or len(first) < 2:
            return None

        x_values = [point.value for point in first]
        y_values = [point.value for point in second]
        x_mean = sum(x_values) / len(x_values)
        y_mean = sum(y_values) / len(y_values)
        denominator = sum((value - x_mean) ** 2 for value in x_values)
        if denominator == 0:
            return None
        numerator = sum(
            (x_value - x_mean) * (y_value - y_mean)
            for x_value, y_value in zip(x_values, y_values, strict=True)
        )
        return numerator / denominator

    def calculate_best_lag_correlation(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
        *,
        max_lag: int,
        min_samples: int = 8,
    ) -> tuple[int | None, float | None, int]:
        if len(first) != len(second):
            raise ValueError("Lagged correlation requires aligned observation lists.")

        first_values = [point.value for point in first]
        second_values = [point.value for point in second]
        best_lag: int | None = None
        best_correlation: float | None = None
        best_samples = 0

        for lag in range(-max_lag, max_lag + 1):
            if lag > 0:
                left = first_values[:-lag]
                right = second_values[lag:]
            elif lag < 0:
                offset = abs(lag)
                left = first_values[offset:]
                right = second_values[:-offset]
            else:
                left = first_values
                right = second_values

            if len(left) < min_samples or len(right) < min_samples:
                continue

            correlation = self._pearson_from_values(left, right)
            if correlation is None:
                continue

            if best_correlation is None or abs(correlation) > abs(best_correlation):
                best_lag = lag
                best_correlation = correlation
                best_samples = len(left)

        return best_lag, best_correlation, best_samples

    @staticmethod
    def standardize(observations: list[ObservationPoint]) -> list[ObservationPoint]:
        if len(observations) < 2:
            return observations

        values = [point.value for point in observations]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        standard_deviation = sqrt(variance)
        if standard_deviation == 0:
            return observations

        return [
            ObservationPoint(
                date=point.date,
                value=(point.value - mean) / standard_deviation,
            )
            for point in observations
        ]

    @staticmethod
    def normalize_to_index(
        observations: list[ObservationPoint],
        *,
        base_value: float = 100.0,
    ) -> list[ObservationPoint]:
        if not observations:
            return []

        first_value = observations[0].value
        if first_value == 0:
            raise ValueError("Cannot normalize a series with a zero starting value.")

        return [
            ObservationPoint(date=point.date, value=(point.value / first_value) * base_value)
            for point in observations
        ]

    @staticmethod
    def calculate_total_growth_pct(observations: list[ObservationPoint]) -> float | None:
        if len(observations) < 2:
            return None

        first_value = observations[0].value
        last_value = observations[-1].value
        if first_value == 0:
            return None

        return ((last_value / first_value) - 1.0) * 100.0

    @staticmethod
    def calculate_cagr_pct(observations: list[ObservationPoint]) -> float | None:
        if len(observations) < 2:
            return None

        first_point = observations[0]
        last_point = observations[-1]
        years = (last_point.date - first_point.date).days / 365.25
        if years <= 0 or first_point.value == 0:
            return None

        return ((last_point.value / first_point.value) ** (1.0 / years) - 1.0) * 100.0

    @staticmethod
    def calculate_average_value(observations: list[ObservationPoint]) -> float | None:
        if not observations:
            return None
        return sum(point.value for point in observations) / len(observations)

    @staticmethod
    def calculate_percentile_rank(
        observations: list[ObservationPoint],
        *,
        value: float | None = None,
    ) -> float | None:
        if len(observations) < 2:
            return None

        reference_value = observations[-1].value if value is None else value
        at_or_below_count = sum(1 for point in observations if point.value <= reference_value)
        return (at_or_below_count / len(observations)) * 100.0

    @staticmethod
    def minimum_point(observations: list[ObservationPoint]) -> ObservationPoint | None:
        if not observations:
            return None
        return min(observations, key=lambda point: (point.value, point.date))

    @staticmethod
    def maximum_point(observations: list[ObservationPoint]) -> ObservationPoint | None:
        if not observations:
            return None
        return max(observations, key=lambda point: (point.value, point.date))

    def summarize_historical_context(
        self,
        observations: list[ObservationPoint],
    ) -> HistoricalSeriesContext | None:
        if not observations:
            return None

        minimum = self.minimum_point(observations)
        maximum = self.maximum_point(observations)
        return HistoricalSeriesContext(
            start_date=observations[0].date,
            end_date=observations[-1].date,
            observation_count=len(observations),
            average_value=self.calculate_average_value(observations),
            percentile_rank=self.calculate_percentile_rank(observations),
            min_value=minimum.value if minimum is not None else None,
            min_date=minimum.date if minimum is not None else None,
            max_value=maximum.value if maximum is not None else None,
            max_date=maximum.date if maximum is not None else None,
        )

    @staticmethod
    def latest_value(observations: list[ObservationPoint]) -> tuple[float | None, date | None]:
        if not observations:
            return None, None
        last_point = observations[-1]
        return last_point.value, last_point.date

    @staticmethod
    def derive_recession_periods(observations: list[ObservationPoint]) -> list[DateSpanAnnotation]:
        if not observations:
            return []

        recession_dates = [point.date for point in observations if point.value >= 1.0]
        if not recession_dates:
            return []

        periods: list[DateSpanAnnotation] = []
        start = recession_dates[0]
        previous = recession_dates[0]

        for current in recession_dates[1:]:
            if (current - previous).days > 40:
                periods.append(DateSpanAnnotation(label="Recession", start_date=start, end_date=previous))
                start = current
            previous = current

        periods.append(DateSpanAnnotation(label="Recession", start_date=start, end_date=previous))
        return periods
