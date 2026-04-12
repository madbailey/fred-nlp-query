from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from fred_query.schemas.analysis import DerivedMetric, HistoricalSeriesContext, ObservationPoint
from fred_query.schemas.intent import TransformType
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesMetadata, SeriesSearchMatch


@dataclass(frozen=True)
class ResolvedSeriesResult:
    resolved_series: ResolvedSeries
    metadata: SeriesMetadata
    search_match: SeriesSearchMatch | None


@dataclass(frozen=True)
class SingleSeriesTransformPlan:
    start_date: date
    end_date: date | None
    effective_transform: TransformType
    normalize_chart: bool
    periods_per_year: int
    transform_window: int | None
    warmup_periods: int
    fetch_start_date: date
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SingleSeriesTransformOutput:
    visible_observations: list[ObservationPoint]
    transformed_observations: list[ObservationPoint] | None
    normalized_observations: list[ObservationPoint] | None
    analysis_basis: str | None
    analysis_units: str | None
    latest_value: float | None
    latest_date: date | None
    comparison_units: str | None
    compare_on_transformed_series: bool
    total_growth_pct: float | None
    compound_annual_growth_rate_pct: float | None


@dataclass(frozen=True)
class RelationshipTransformPlan:
    start_date: date
    end_date: date | None
    frequency_code: str
    frequency_label: str
    periods_per_year: int
    lag_unit: str
    requested_transform: TransformType
    effective_transform: TransformType
    normalization: bool
    transform_window: int | None
    warmup_periods: int
    fetch_start_date: date
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationshipSeriesTransformOutput:
    visible_observations: list[ObservationPoint]
    transformed_observations: list[ObservationPoint]
    basis: str
    units: str
    applied_transform_window: int | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationshipMetricsResult:
    same_period_correlation: float | None
    regression_slope: float | None
    best_lag: int | None
    best_lag_correlation: float | None
    best_lag_samples: int


@dataclass(frozen=True)
class HistoricalSummaryResult:
    context: HistoricalSeriesContext | None
    metrics: list[DerivedMetric]
    warnings: list[str] = field(default_factory=list)
