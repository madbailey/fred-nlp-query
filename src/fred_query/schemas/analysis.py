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
    value: float | str
    unit: str | None = None
    description: str | None = None


class SeriesAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series: ResolvedSeries
    observations: list[ObservationPoint] = Field(default_factory=list)
    transformed_observations: list[ObservationPoint] | None = None
    total_growth_pct: float | None = None
    compound_annual_growth_rate_pct: float | None = None
    latest_value: float | None = None
    latest_observation_date: date | None = None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series_results: list[SeriesAnalysis] = Field(default_factory=list)
    derived_metrics: list[DerivedMetric] = Field(default_factory=list)
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
