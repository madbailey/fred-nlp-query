from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from fred_query.schemas.chart import ChartSpec
from fred_query.schemas.intent import QueryIntent
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesSearchMatch


class ObservationPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: date
    value: float


class DerivedMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    value: float | int | str
    unit: str | None = None
    label: str | None = None
    description: str | None = None


class HistoricalSeriesContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start_date: date
    end_date: date
    observation_count: int
    average_value: float | None = None
    percentile_rank: float | None = None
    min_value: float | None = None
    min_date: date | None = None
    max_value: float | None = None
    max_date: date | None = None


class FollowUpSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    query: str
    label: str | None = None


class RelationshipSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    analysis_basis: str | None = None
    common_frequency: str | None = None
    overlap_observations: int | None = None
    same_period_correlation: float | None = None
    regression_slope: float | None = None
    strongest_lag_periods: int | None = None
    strongest_lag_unit: str | None = None
    strongest_lag_correlation: float | None = None
    strongest_lag_observations: int | None = None


class CrossSectionSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    snapshot_basis: str
    resolved_series_count: int
    displayed_series_count: int
    display_selection_basis: str
    rank_order: str
    leader_label: str
    leader_value: float | None = None
    leader_unit: str | None = None


class SeriesAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series: ResolvedSeries
    observations: list[ObservationPoint] = Field(default_factory=list)
    transformed_observations: list[ObservationPoint] | None = None
    historical_context: HistoricalSeriesContext | None = None
    analysis_basis: str | None = None
    analysis_units: str | None = None
    total_growth_pct: float | None = None
    compound_annual_growth_rate_pct: float | None = None
    latest_value: float | None = None
    latest_observation_date: date | None = None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series_results: list[SeriesAnalysis] = Field(default_factory=list)
    derived_metrics: list[DerivedMetric] = Field(default_factory=list)
    relationship_summary: RelationshipSummary | None = None
    cross_section_summary: CrossSectionSummary | None = None
    warnings: list[str] = Field(default_factory=list)
    latest_observation_date: date | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: QueryIntent
    analysis: AnalysisResult
    chart: ChartSpec
    answer_text: str


class RoutedQueryStatus(str, Enum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class RoutedQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: RoutedQueryStatus
    intent: QueryIntent
    answer_text: str
    query_response: QueryResponse | None = None
    candidate_series: list[SeriesSearchMatch] = Field(default_factory=list)
