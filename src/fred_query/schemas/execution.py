from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from fred_query.schemas.intent import QueryIntent


class ExecutionPlanType(str, Enum):
    SINGLE_SERIES = "single_series"
    CROSS_SECTION = "cross_section"
    STATE_COMPARE = "state_compare"
    RELATIONSHIP = "relationship"


class ExecutionOperation(str, Enum):
    SINGLE_SERIES_LOOKUP = "single_series_lookup"
    CROSS_SECTION_ANALYSIS = "cross_section_analysis"
    STATE_GDP_COMPARISON = "state_gdp_comparison"
    RELATIONSHIP_ANALYSIS = "relationship_analysis"


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str
    operation: ExecutionOperation
    input_intent: QueryIntent
    output_key: str = "query_response"


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plan_type: ExecutionPlanType
    source_intent: QueryIntent
    steps: list[ExecutionStep] = Field(min_length=1)
    final_step_id: str
