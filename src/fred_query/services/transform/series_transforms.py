from __future__ import annotations

from datetime import date
from math import sqrt

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.intent import TransformType
from fred_query.services.transform.models import SingleSeriesTransformResult
from fred_query.services.transform.planning import TransformPlanningService


class SeriesTransformService:
    def __init__(
        self,
        planning_service: TransformPlanningService | None = None,
    ) -> None:
        self.planning_service = planning_service or TransformPlanningService()

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

        periods_per_year = self.planning_service.periods_per_year_for_frequency(frequency)

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

        applied_window, warnings = self.planning_service.resolve_transform_window(
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
