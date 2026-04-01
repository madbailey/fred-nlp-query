from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import HistoricalSeriesContext, ObservationPoint
from fred_query.schemas.chart import DateSpanAnnotation
from fred_query.schemas.intent import TransformType
from fred_query.services.transform import (
    RelationshipTransformService,
    SeriesStatisticsService,
    SeriesTransformService,
    SingleSeriesTransformResult,
    TransformPlanningService,
)


class TransformService:
    """Compatibility facade over the split transform helpers."""

    def __init__(
        self,
        *,
        planning_service: TransformPlanningService | None = None,
        series_transform_service: SeriesTransformService | None = None,
        relationship_transform_service: RelationshipTransformService | None = None,
        series_statistics_service: SeriesStatisticsService | None = None,
    ) -> None:
        self.planning_service = planning_service or TransformPlanningService()
        self.series_transform_service = series_transform_service or SeriesTransformService(self.planning_service)
        self.relationship_transform_service = relationship_transform_service or RelationshipTransformService(
            self.series_transform_service
        )
        self.series_statistics_service = series_statistics_service or SeriesStatisticsService()

    def choose_relationship_frequency(
        self,
        frequencies: list[str],
    ) -> tuple[str, str, int, str]:
        return self.relationship_transform_service.choose_relationship_frequency(frequencies)

    def periods_per_year_for_frequency(self, frequency: str | None) -> int:
        return self.planning_service.periods_per_year_for_frequency(frequency)

    def subtract_periods(
        self,
        value: date,
        *,
        periods: int,
        frequency: str | None,
    ) -> date:
        return self.planning_service.subtract_periods(value, periods=periods, frequency=frequency)

    def default_window_for_transform(
        self,
        *,
        transform: TransformType,
        frequency: str | None,
    ) -> int | None:
        return self.planning_service.default_window_for_transform(transform=transform, frequency=frequency)

    def resolve_transform_window(
        self,
        *,
        transform: TransformType,
        frequency: str | None,
        requested_window: int | None,
    ) -> tuple[int | None, list[str]]:
        return self.planning_service.resolve_transform_window(
            transform=transform,
            frequency=frequency,
            requested_window=requested_window,
        )

    def transform_warmup_periods(
        self,
        *,
        transform: TransformType,
        periods_per_year: int,
        window: int | None,
    ) -> int:
        return self.planning_service.transform_warmup_periods(
            transform=transform,
            periods_per_year=periods_per_year,
            window=window,
        )

    def relationship_max_lag(self, periods_per_year: int) -> int:
        return self.relationship_transform_service.relationship_max_lag(periods_per_year)

    def calculate_pct_change(
        self,
        observations: list[ObservationPoint],
        *,
        periods: int,
    ) -> list[ObservationPoint]:
        return self.series_transform_service.calculate_pct_change(observations, periods=periods)

    def cumulative_growth_series(self, observations: list[ObservationPoint]) -> list[ObservationPoint]:
        return self.series_transform_service.cumulative_growth_series(observations)

    def rolling_average(
        self,
        observations: list[ObservationPoint],
        *,
        window: int,
    ) -> list[ObservationPoint]:
        return self.series_transform_service.rolling_average(observations, window=window)

    def rolling_stddev(
        self,
        observations: list[ObservationPoint],
        *,
        window: int,
    ) -> list[ObservationPoint]:
        return self.series_transform_service.rolling_stddev(observations, window=window)

    def rolling_volatility(
        self,
        observations: list[ObservationPoint],
        *,
        window: int,
        periods_per_year: int,
    ) -> list[ObservationPoint]:
        return self.series_transform_service.rolling_volatility(
            observations,
            window=window,
            periods_per_year=periods_per_year,
        )

    def filter_observations_by_date(
        self,
        observations: list[ObservationPoint],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ObservationPoint]:
        return self.series_transform_service.filter_observations_by_date(
            observations,
            start_date=start_date,
            end_date=end_date,
        )

    def apply_single_series_transform(
        self,
        observations: list[ObservationPoint],
        *,
        transform: TransformType,
        units: str,
        frequency: str | None,
        window: int | None = None,
    ) -> SingleSeriesTransformResult:
        return self.series_transform_service.apply_single_series_transform(
            observations,
            transform=transform,
            units=units,
            frequency=frequency,
            window=window,
        )

    def should_use_level_relationship(self, title: str, units: str) -> bool:
        return self.relationship_transform_service.should_use_level_relationship(title, units)

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
        return self.relationship_transform_service.build_relationship_basis(
            observations,
            title=title,
            units=units,
            frequency=frequency,
            periods_per_year=periods_per_year,
            transform=transform,
            normalization=normalization,
            requested_window=requested_window,
        )

    def align_on_dates(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
    ) -> tuple[list[ObservationPoint], list[ObservationPoint]]:
        return self.relationship_transform_service.align_on_dates(first, second)

    def calculate_correlation(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
    ) -> float | None:
        return self.relationship_transform_service.calculate_correlation(first, second)

    def calculate_regression_slope(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
    ) -> float | None:
        return self.relationship_transform_service.calculate_regression_slope(first, second)

    def calculate_best_lag_correlation(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
        *,
        max_lag: int,
        min_samples: int = 8,
    ) -> tuple[int | None, float | None, int]:
        return self.relationship_transform_service.calculate_best_lag_correlation(
            first,
            second,
            max_lag=max_lag,
            min_samples=min_samples,
        )

    def standardize(self, observations: list[ObservationPoint]) -> list[ObservationPoint]:
        return self.relationship_transform_service.standardize(observations)

    def normalize_to_index(
        self,
        observations: list[ObservationPoint],
        *,
        base_value: float = 100.0,
    ) -> list[ObservationPoint]:
        return self.series_transform_service.normalize_to_index(observations, base_value=base_value)

    def calculate_total_growth_pct(self, observations: list[ObservationPoint]) -> float | None:
        return self.series_statistics_service.calculate_total_growth_pct(observations)

    def calculate_cagr_pct(self, observations: list[ObservationPoint]) -> float | None:
        return self.series_statistics_service.calculate_cagr_pct(observations)

    def calculate_average_value(self, observations: list[ObservationPoint]) -> float | None:
        return self.series_statistics_service.calculate_average_value(observations)

    def calculate_percentile_rank(
        self,
        observations: list[ObservationPoint],
        *,
        value: float | None = None,
    ) -> float | None:
        return self.series_statistics_service.calculate_percentile_rank(observations, value=value)

    def minimum_point(self, observations: list[ObservationPoint]) -> ObservationPoint | None:
        return self.series_statistics_service.minimum_point(observations)

    def maximum_point(self, observations: list[ObservationPoint]) -> ObservationPoint | None:
        return self.series_statistics_service.maximum_point(observations)

    def summarize_historical_context(
        self,
        observations: list[ObservationPoint],
    ) -> HistoricalSeriesContext | None:
        return self.series_statistics_service.summarize_historical_context(observations)

    def latest_value(self, observations: list[ObservationPoint]) -> tuple[float | None, date | None]:
        return self.series_statistics_service.latest_value(observations)

    def derive_recession_periods(self, observations: list[ObservationPoint]) -> list[DateSpanAnnotation]:
        return self.series_statistics_service.derive_recession_periods(observations)
