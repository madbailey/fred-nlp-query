from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import AnalysisResult, QueryResponse, RoutedQueryStatus
from fred_query.schemas.chart import AxisSpec, ChartSpec
from fred_query.schemas.intent import ComparisonMode, QueryIntent, TaskType
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
        assert relationship_service.last_intent is not None
        self.assertEqual(relationship_service.last_intent.series_ids, ["UNRATE", "CPIAUCSL"])
        self.assertFalse(relationship_service.last_intent.clarification_needed)


if __name__ == "__main__":
    unittest.main()
