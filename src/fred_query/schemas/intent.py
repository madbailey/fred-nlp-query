from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskType(str, Enum):
    SINGLE_SERIES_LOOKUP = "single_series_lookup"
    CROSS_SECTION = "cross_section"
    STATE_GDP_COMPARISON = "state_gdp_comparison"
    MULTI_SERIES_COMPARISON = "multi_series_comparison"
    RELATIONSHIP_ANALYSIS = "relationship_analysis"


class ComparisonMode(str, Enum):
    NONE = "none"
    CROSS_SECTION = "cross_section"
    STATE_VS_STATE = "state_vs_state"
    MULTI_SERIES = "multi_series"
    RELATIONSHIP = "relationship"


class TransformType(str, Enum):
    LEVEL = "level"
    NORMALIZED_INDEX = "normalized_index"
    TOTAL_GROWTH = "total_growth"
    YEAR_OVER_YEAR_PERCENT_CHANGE = "year_over_year_percent_change"
    PERIOD_OVER_PERIOD_PERCENT_CHANGE = "period_over_period_percent_change"
    ROLLING_AVERAGE = "rolling_average"
    ROLLING_STDDEV = "rolling_stddev"
    ROLLING_VOLATILITY = "rolling_volatility"


class GeographyType(str, Enum):
    UNKNOWN = "unknown"
    STATE = "state"
    NATIONAL = "national"
    REGION = "region"


class CrossSectionScope(str, Enum):
    SINGLE_SERIES = "single_series"
    PROVIDED_GEOGRAPHIES = "provided_geographies"
    STATES = "states"


class QueryOperator(str, Enum):
    LOOKUP = "lookup"
    COMPARE = "compare"
    RANK = "rank"
    ANALYZE_RELATIONSHIP = "analyze_relationship"


class QueryOutputMode(str, Enum):
    TIME_SERIES = "time_series"
    CROSS_SECTION = "cross_section"
    RELATIONSHIP = "relationship"


class TimeScopeKind(str, Enum):
    UNSPECIFIED = "unspecified"
    RANGE = "range"
    POINT_IN_TIME = "point_in_time"
    LATEST = "latest"


class QueryTimeScope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: TimeScopeKind = TimeScopeKind.UNSPECIFIED
    start_date: date | None = None
    end_date: date | None = None
    observation_date: date | None = None


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subjects: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    time_scope: QueryTimeScope = Field(default_factory=QueryTimeScope)
    operators: list[QueryOperator] = Field(default_factory=list)
    output_mode: QueryOutputMode = QueryOutputMode.TIME_SERIES


class Geography(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    geography_type: GeographyType = GeographyType.UNKNOWN
    code: str | None = None


class QueryIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_type: TaskType
    original_query: str | None = None
    indicators: list[str] = Field(default_factory=list)
    geographies: list[Geography] = Field(default_factory=list)
    comparison_mode: ComparisonMode = ComparisonMode.NONE
    start_date: date | None = None
    end_date: date | None = None
    observation_date: date | None = None
    frequency: str | None = None
    transform: TransformType = TransformType.LEVEL
    transform_window: int | None = Field(default=None, ge=2, le=1000)
    normalization: bool = False
    units_preference: str | None = None
    cross_section_scope: CrossSectionScope | None = None
    rank_limit: int | None = Field(default=None, ge=1, le=100)
    sort_descending: bool = True
    needs_latest_value: bool = True
    needs_chart: bool = True
    needs_revision_analysis: bool = False
    clarification_needed: bool = False
    clarification_question: str | None = None
    clarification_target_index: int | None = None
    search_text: str | None = None
    search_texts: list[str] = Field(default_factory=list)
    series_id: str | None = None
    series_ids: list[str | None] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)
    query_plan: QueryPlan | None = None

    @model_validator(mode="after")
    def _initialize_query_plan(self) -> QueryIntent:
        if self.query_plan is None:
            self.query_plan = self._build_query_plan()
        else:
            self.task_type = self.planned_task_type
        return self

    @property
    def planned_task_type(self) -> TaskType:
        if self.query_plan is None:
            return self.task_type
        if self.query_plan.output_mode == QueryOutputMode.RELATIONSHIP:
            return TaskType.RELATIONSHIP_ANALYSIS
        if self.query_plan.output_mode == QueryOutputMode.CROSS_SECTION:
            return TaskType.CROSS_SECTION
        if QueryOperator.COMPARE in self.query_plan.operators:
            return (
                TaskType.STATE_GDP_COMPARISON
                if self._is_state_gdp_comparison_plan(self.query_plan)
                else TaskType.MULTI_SERIES_COMPARISON
            )
        return TaskType.SINGLE_SERIES_LOOKUP

    def refresh_query_plan(self) -> QueryIntent:
        self.query_plan = self._build_query_plan()
        self.task_type = self.planned_task_type
        return self

    def _build_query_plan(self) -> QueryPlan:
        return QueryPlan(
            subjects=self._subjects_for_plan(),
            geographies=[item.name for item in self.geographies if item.name],
            time_scope=self._time_scope_for_plan(),
            operators=self._operators_for_plan(),
            output_mode=self._output_mode_for_plan(),
        )

    def _subjects_for_plan(self) -> list[str]:
        values: list[str] = []
        for candidate in [
            *self.indicators,
            self.search_text,
            self.series_id,
            *self.search_texts,
            *self.series_ids,
        ]:
            if not candidate:
                continue
            if candidate not in values:
                values.append(candidate)
        return values

    def _time_scope_for_plan(self) -> QueryTimeScope:
        if self.observation_date is not None:
            return QueryTimeScope(
                kind=TimeScopeKind.POINT_IN_TIME,
                observation_date=self.observation_date,
                start_date=self.start_date,
                end_date=self.end_date,
            )
        if self.start_date is not None or self.end_date is not None:
            return QueryTimeScope(
                kind=TimeScopeKind.RANGE,
                start_date=self.start_date,
                end_date=self.end_date,
            )
        if self.task_type == TaskType.CROSS_SECTION and self.needs_latest_value:
            return QueryTimeScope(kind=TimeScopeKind.LATEST)
        return QueryTimeScope(kind=TimeScopeKind.UNSPECIFIED)

    def _operators_for_plan(self) -> list[QueryOperator]:
        if self.task_type == TaskType.RELATIONSHIP_ANALYSIS:
            return [QueryOperator.ANALYZE_RELATIONSHIP]
        if self.task_type in (TaskType.STATE_GDP_COMPARISON, TaskType.MULTI_SERIES_COMPARISON):
            return [QueryOperator.COMPARE]
        if self.task_type == TaskType.CROSS_SECTION:
            if self.cross_section_scope in (
                CrossSectionScope.STATES,
                CrossSectionScope.PROVIDED_GEOGRAPHIES,
            ) or self.rank_limit is not None:
                return [QueryOperator.RANK]
            return [QueryOperator.LOOKUP]
        return [QueryOperator.LOOKUP]

    def _output_mode_for_plan(self) -> QueryOutputMode:
        if self.task_type == TaskType.RELATIONSHIP_ANALYSIS:
            return QueryOutputMode.RELATIONSHIP
        if self.task_type == TaskType.CROSS_SECTION:
            return QueryOutputMode.CROSS_SECTION
        return QueryOutputMode.TIME_SERIES

    def _is_state_gdp_comparison_plan(self, query_plan: QueryPlan) -> bool:
        if len(self.geographies) != 2:
            return False
        if any(item.geography_type != GeographyType.STATE for item in self.geographies):
            return False
        subjects = [subject.strip().lower() for subject in query_plan.subjects if subject and subject.strip()]
        if not subjects:
            return self.task_type == TaskType.STATE_GDP_COMPARISON
        return all("gdp" in subject for subject in subjects)
