from __future__ import annotations

from math import sqrt
from datetime import date

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.chart import DateSpanAnnotation


class TransformService:
    """Deterministic transforms and derived metrics."""

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
        periods_per_year: int,
    ) -> tuple[list[ObservationPoint], str, str]:
        if self.should_use_level_relationship(title, units):
            return observations, "Reported level", units

        if periods_per_year > 1:
            year_over_year = self.calculate_pct_change(observations, periods=periods_per_year)
            if len(year_over_year) >= max(8, periods_per_year):
                return year_over_year, "Year-over-year percent change", "Percent"

        period_change = self.calculate_pct_change(observations, periods=1)
        if period_change:
            return period_change, "Period-over-period percent change", "Percent"

        return observations, "Reported level", units

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
