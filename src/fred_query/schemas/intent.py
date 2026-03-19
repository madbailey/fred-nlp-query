from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskType(str, Enum):
    SINGLE_SERIES_LOOKUP = "single_series_lookup"
    STATE_GDP_COMPARISON = "state_gdp_comparison"
    MULTI_SERIES_COMPARISON = "multi_series_comparison"
    RELATIONSHIP_ANALYSIS = "relationship_analysis"


class ComparisonMode(str, Enum):
    NONE = "none"
    STATE_VS_STATE = "state_vs_state"
    MULTI_SERIES = "multi_series"
    RELATIONSHIP = "relationship"


class TransformType(str, Enum):
    LEVEL = "level"
    NORMALIZED_INDEX = "normalized_index"
    TOTAL_GROWTH = "total_growth"


class GeographyType(str, Enum):
    UNKNOWN = "unknown"
    STATE = "state"
    NATIONAL = "national"
    REGION = "region"


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
    frequency: str | None = None
    transform: TransformType = TransformType.LEVEL
    normalization: bool = False
    units_preference: str | None = None
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
