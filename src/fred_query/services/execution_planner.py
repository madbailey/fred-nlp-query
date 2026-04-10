from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.execution import (
    ExecutionOperation,
    ExecutionPlan,
    ExecutionPlanType,
    ExecutionStep,
)
from fred_query.schemas.intent import QueryIntent, TaskType


class ExecutionPlanner:
    """Compile parser-facing QueryIntent into a deterministic execution plan."""

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @staticmethod
    def supports(intent: QueryIntent) -> bool:
        return intent.planned_task_type in {
            TaskType.SINGLE_SERIES_LOOKUP,
            TaskType.CROSS_SECTION,
            TaskType.STATE_GDP_COMPARISON,
            TaskType.MULTI_SERIES_COMPARISON,
            TaskType.RELATIONSHIP_ANALYSIS,
        }

    def compile(self, intent: QueryIntent) -> ExecutionPlan:
        task_type = intent.planned_task_type
        if task_type == TaskType.SINGLE_SERIES_LOOKUP:
            return self._single_step_plan(
                intent,
                plan_type=ExecutionPlanType.SINGLE_SERIES,
                operation=ExecutionOperation.SINGLE_SERIES_LOOKUP,
                step_id="single_series_lookup",
            )
        if task_type == TaskType.CROSS_SECTION:
            return self._single_step_plan(
                intent,
                plan_type=ExecutionPlanType.CROSS_SECTION,
                operation=ExecutionOperation.CROSS_SECTION_ANALYSIS,
                step_id="cross_section_analysis",
            )
        if task_type == TaskType.STATE_GDP_COMPARISON:
            execution_intent = intent.model_copy(deep=True)
            execution_intent.start_date = execution_intent.start_date or self._default_start_date()
            return self._single_step_plan(
                execution_intent,
                plan_type=ExecutionPlanType.STATE_COMPARE,
                operation=ExecutionOperation.STATE_GDP_COMPARISON,
                step_id="state_gdp_comparison",
                source_intent=intent,
            )
        if task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            return self._single_step_plan(
                intent,
                plan_type=ExecutionPlanType.RELATIONSHIP,
                operation=ExecutionOperation.RELATIONSHIP_ANALYSIS,
                step_id="relationship_analysis",
            )

        raise ValueError(f"No execution plan is available for task type {task_type!r}.")

    @staticmethod
    def _single_step_plan(
        intent: QueryIntent,
        *,
        plan_type: ExecutionPlanType,
        operation: ExecutionOperation,
        step_id: str,
        source_intent: QueryIntent | None = None,
    ) -> ExecutionPlan:
        return ExecutionPlan(
            plan_type=plan_type,
            source_intent=source_intent or intent,
            steps=[
                ExecutionStep(
                    step_id=step_id,
                    operation=operation,
                    input_intent=intent,
                )
            ],
            final_step_id=step_id,
        )
