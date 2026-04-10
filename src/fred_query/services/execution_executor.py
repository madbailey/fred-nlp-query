from __future__ import annotations

from fred_query.schemas.analysis import QueryResponse
from fred_query.schemas.execution import ExecutionOperation, ExecutionPlan, ExecutionStep
from fred_query.services.comparison_service import StateGDPComparisonService
from fred_query.services.cross_section_service import CrossSectionService
from fred_query.services.relationship_service import RelationshipAnalysisService
from fred_query.services.single_series_service import SingleSeriesLookupService


class ExecutionExecutor:
    """Run validated execution plans through the existing deterministic services."""

    def __init__(
        self,
        *,
        state_gdp_service: StateGDPComparisonService,
        cross_section_service: CrossSectionService,
        single_series_service: SingleSeriesLookupService,
        relationship_service: RelationshipAnalysisService,
    ) -> None:
        self.state_gdp_service = state_gdp_service
        self.cross_section_service = cross_section_service
        self.single_series_service = single_series_service
        self.relationship_service = relationship_service

    def execute(self, plan: ExecutionPlan) -> QueryResponse:
        if len(plan.steps) != 1:
            raise ValueError("The phase-one executor only supports single-step execution plans.")
        return self._execute_step(plan.steps[0])

    def _execute_step(self, step: ExecutionStep) -> QueryResponse:
        intent = step.input_intent
        if step.operation == ExecutionOperation.SINGLE_SERIES_LOOKUP:
            return self.single_series_service.lookup(intent)
        if step.operation == ExecutionOperation.CROSS_SECTION_ANALYSIS:
            return self.cross_section_service.analyze(intent)
        if step.operation == ExecutionOperation.RELATIONSHIP_ANALYSIS:
            return self.relationship_service.analyze(intent)
        if step.operation == ExecutionOperation.STATE_GDP_COMPARISON:
            if len(intent.geographies) != 2:
                raise ValueError("State GDP comparison execution requires exactly two geographies.")
            if intent.start_date is None:
                raise ValueError("State GDP comparison execution requires a start date.")
            return self.state_gdp_service.compare(
                state1=intent.geographies[0].name,
                state2=intent.geographies[1].name,
                start_date=intent.start_date,
                end_date=intent.end_date,
                normalize=intent.normalization,
            )

        raise ValueError(f"Unsupported execution operation {step.operation!r}.")
