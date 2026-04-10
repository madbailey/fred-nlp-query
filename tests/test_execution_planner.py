from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.execution import ExecutionOperation, ExecutionPlanType
from fred_query.schemas.intent import (
    ComparisonMode,
    CrossSectionScope,
    Geography,
    GeographyType,
    QueryIntent,
    TaskType,
)
from fred_query.services.execution_planner import ExecutionPlanner


class ExecutionPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = ExecutionPlanner()

    def test_compiles_single_series_intent_to_single_series_plan(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            search_text="unemployment rate",
            start_date=date(2020, 1, 1),
        )

        plan = self.planner.compile(intent)

        self.assertEqual(plan.plan_type, ExecutionPlanType.SINGLE_SERIES)
        self.assertEqual(plan.steps[0].operation, ExecutionOperation.SINGLE_SERIES_LOOKUP)
        self.assertEqual(plan.steps[0].input_intent, intent)
        self.assertEqual(plan.final_step_id, "single_series_lookup")

    def test_compiles_cross_section_intent_to_cross_section_plan(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            comparison_mode=ComparisonMode.CROSS_SECTION,
            cross_section_scope=CrossSectionScope.STATES,
            search_text="unemployment rate",
        )

        plan = self.planner.compile(intent)

        self.assertEqual(plan.plan_type, ExecutionPlanType.CROSS_SECTION)
        self.assertEqual(plan.steps[0].operation, ExecutionOperation.CROSS_SECTION_ANALYSIS)

    def test_compiles_state_gdp_intent_to_state_compare_plan_with_default_start_date(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
            ],
        )

        plan = self.planner.compile(intent)

        self.assertEqual(plan.plan_type, ExecutionPlanType.STATE_COMPARE)
        self.assertEqual(plan.steps[0].operation, ExecutionOperation.STATE_GDP_COMPARISON)
        self.assertIsNone(plan.source_intent.start_date)
        self.assertIsNotNone(plan.steps[0].input_intent.start_date)

    def test_compiles_multi_series_intent_to_relationship_execution_plan(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.MULTI_SERIES_COMPARISON,
            comparison_mode=ComparisonMode.MULTI_SERIES,
            search_texts=["unemployment rate", "cpi"],
        )

        plan = self.planner.compile(intent)

        self.assertEqual(plan.plan_type, ExecutionPlanType.RELATIONSHIP)
        self.assertEqual(plan.steps[0].operation, ExecutionOperation.RELATIONSHIP_ANALYSIS)


if __name__ == "__main__":
    unittest.main()
