from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import AnalysisResult, QueryResponse, RoutedQueryReason, RoutedQueryStatus
from fred_query.schemas.chart import AxisSpec, ChartSpec
from fred_query.schemas.intent import (
    ComparisonMode,
    Geography,
    GeographyType,
    QueryIntent,
    QueryOperator,
    QueryOutputMode,
    QueryPlan,
    QueryTimeScope,
    TaskType,
)
from fred_query.services.clarification_resolver import ClarificationResolver
from fred_query.services.query_router import QueryRouter


class _NoopClarificationResolver(ClarificationResolver):
    def __init__(self) -> None:
        pass

    def build_candidates(self, intent: QueryIntent) -> list[object]:
        return []

    def answer_text(self, intent: QueryIntent, *, candidate_series: list[object]) -> str:
        return "clarification"


class _StubStateGDPService:
    def compare(self, **_: object) -> QueryResponse:
        raise AssertionError("state GDP route should not be used")


class _StubCrossSectionService:
    def analyze(self, intent: QueryIntent) -> QueryResponse:
        raise AssertionError("cross-section route should not be used")


class _CapturingRelationshipService:
    def __init__(self) -> None:
        self.last_intent: QueryIntent | None = None

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        self.last_intent = intent
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(coverage_start=date(2020, 1, 1), coverage_end=date(2024, 1, 1)),
            chart=ChartSpec(
                title="Relationship",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Value"),
                source_note="Source: fixture",
            ),
            answer_text="relationship",
        )


class _StubSingleSeriesService:
    def lookup(self, intent: QueryIntent) -> QueryResponse:
        raise AssertionError("single-series route should not be used")


class QueryRouterTest(unittest.TestCase):
    def test_route_applies_selected_series_ids_before_relationship_dispatch(self) -> None:
        relationship_service = _CapturingRelationshipService()
        router = QueryRouter(
            clarification_resolver=_NoopClarificationResolver(),
            state_gdp_service=_StubStateGDPService(),
            cross_section_service=_StubCrossSectionService(),
            single_series_service=_StubSingleSeriesService(),
            relationship_service=relationship_service,
        )
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            comparison_mode=ComparisonMode.RELATIONSHIP,
            clarification_needed=True,
            clarification_target_index=1,
            search_texts=["unemployment rate", "inflation"],
        )

        response = router.route(intent, selected_series_ids=["UNRATE", "CPIAUCSL"])

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        assert relationship_service.last_intent is not None
        self.assertEqual(relationship_service.last_intent.series_ids, ["UNRATE", "CPIAUCSL"])
        self.assertFalse(relationship_service.last_intent.clarification_needed)

    def test_route_uses_query_plan_above_legacy_task_type(self) -> None:
        relationship_service = _CapturingRelationshipService()
        router = QueryRouter(
            clarification_resolver=_NoopClarificationResolver(),
            state_gdp_service=_StubStateGDPService(),
            cross_section_service=_StubCrossSectionService(),
            single_series_service=_StubSingleSeriesService(),
            relationship_service=relationship_service,
        )
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            query_plan=QueryPlan(
                subjects=["unemployment rate", "inflation"],
                geographies=[],
                time_scope=QueryTimeScope(),
                operators=[QueryOperator.ANALYZE_RELATIONSHIP],
                output_mode=QueryOutputMode.RELATIONSHIP,
            ),
            search_texts=["unemployment rate", "inflation"],
            comparison_mode=ComparisonMode.RELATIONSHIP,
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        assert relationship_service.last_intent is not None
        self.assertEqual(relationship_service.last_intent.task_type, TaskType.RELATIONSHIP_ANALYSIS)

    def test_mixed_state_comparison_does_not_reclassify_as_state_gdp(self) -> None:
        relationship_service = _CapturingRelationshipService()
        router = QueryRouter(
            clarification_resolver=_NoopClarificationResolver(),
            state_gdp_service=_StubStateGDPService(),
            cross_section_service=_StubCrossSectionService(),
            single_series_service=_StubSingleSeriesService(),
            relationship_service=relationship_service,
        )
        intent = QueryIntent(
            task_type=TaskType.MULTI_SERIES_COMPARISON,
            comparison_mode=ComparisonMode.MULTI_SERIES,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
            ],
            indicators=["state gdp", "unemployment rate"],
            search_texts=["state gdp california texas", "unemployment rate california texas"],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        assert relationship_service.last_intent is not None
        self.assertEqual(relationship_service.last_intent.task_type, TaskType.MULTI_SERIES_COMPARISON)

    def test_state_gdp_clarification_uses_unknown_geography_reason_for_missing_state(self) -> None:
        router = QueryRouter(
            clarification_resolver=_NoopClarificationResolver(),
            state_gdp_service=_StubStateGDPService(),
            cross_section_service=_StubCrossSectionService(),
            single_series_service=_StubSingleSeriesService(),
            relationship_service=_CapturingRelationshipService(),
        )
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            clarification_needed=True,
            geographies=[Geography(name="California", geography_type=GeographyType.STATE)],
            comparison_mode=ComparisonMode.STATE_VS_STATE,
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.UNKNOWN_GEOGRAPHY)

    def test_state_gdp_clarification_uses_too_many_targets_reason_for_extra_states(self) -> None:
        router = QueryRouter(
            clarification_resolver=_NoopClarificationResolver(),
            state_gdp_service=_StubStateGDPService(),
            cross_section_service=_StubCrossSectionService(),
            single_series_service=_StubSingleSeriesService(),
            relationship_service=_CapturingRelationshipService(),
        )
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            clarification_needed=True,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
                Geography(name="New York", geography_type=GeographyType.STATE),
            ],
            comparison_mode=ComparisonMode.STATE_VS_STATE,
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.TOO_MANY_TARGETS)

    def test_unsupported_route_returns_machine_readable_reason(self) -> None:
        router = QueryRouter(
            clarification_resolver=_NoopClarificationResolver(),
            state_gdp_service=_StubStateGDPService(),
            cross_section_service=_StubCrossSectionService(),
            single_series_service=_StubSingleSeriesService(),
            relationship_service=_CapturingRelationshipService(),
        )
        intent = QueryIntent.model_construct(task_type="custom_task", query_plan=None)

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.UNSUPPORTED)
        self.assertEqual(response.reason, RoutedQueryReason.UNSUPPORTED_ROUTE)


if __name__ == "__main__":
    unittest.main()
