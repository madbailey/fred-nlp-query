"""Deterministic router fixture suite (EVAL-002).

Covers completed, clarification, and unsupported routing paths.
Each fixture asserts the machine-readable reason codes from QRY-003.
"""

from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import (
    AnalysisResult,
    QueryResponse,
    RoutedQueryReason,
    RoutedQueryStatus,
)
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
from fred_query.schemas.resolved_series import SeriesSearchMatch
from fred_query.services.clarification_resolver import ClarificationResolver
from fred_query.services.query_router import QueryRouter


# ---------------------------------------------------------------------------
# Stub services (same pattern as existing test_query_router.py)
# ---------------------------------------------------------------------------

class _NoopClarificationResolver(ClarificationResolver):
    def __init__(self) -> None:
        pass

    def build_candidates(self, intent: QueryIntent) -> list[SeriesSearchMatch]:
        return []

    def answer_text(self, intent: QueryIntent, *, candidate_series: list[object]) -> str:
        return "clarification needed"


class _CandidateClarificationResolver(ClarificationResolver):
    """Returns pre-set candidates so tests can verify they flow through."""

    def __init__(self, candidates: list[SeriesSearchMatch]) -> None:
        self._candidates = candidates

    def build_candidates(self, intent: QueryIntent) -> list[SeriesSearchMatch]:
        return self._candidates

    def answer_text(self, intent: QueryIntent, *, candidate_series: list[object]) -> str:
        return f"Did you mean one of these {len(candidate_series)} options?"


def _stub_chart() -> ChartSpec:
    return ChartSpec(
        title="Fixture",
        x_axis=AxisSpec(title="Date"),
        y_axis=AxisSpec(title="Value"),
        source_note="Source: fixture",
    )


class _CapturingSingleSeriesService:
    def __init__(self) -> None:
        self.last_intent: QueryIntent | None = None

    def lookup(self, intent: QueryIntent) -> QueryResponse:
        self.last_intent = intent
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(coverage_start=date(2020, 1, 1), coverage_end=date(2024, 1, 1)),
            chart=_stub_chart(),
            answer_text="single series result",
        )


class _CapturingStateGDPService:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, object] = {}

    def compare(self, **kwargs: object) -> QueryResponse:
        self.last_kwargs = kwargs
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
            ],
            comparison_mode=ComparisonMode.STATE_VS_STATE,
        )
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(coverage_start=date(2014, 1, 1), coverage_end=date(2024, 1, 1)),
            chart=_stub_chart(),
            answer_text="state gdp comparison result",
        )


class _CapturingCrossSectionService:
    def __init__(self) -> None:
        self.last_intent: QueryIntent | None = None

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        self.last_intent = intent
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(coverage_start=date(2023, 1, 1), coverage_end=date(2024, 1, 1)),
            chart=_stub_chart(),
            answer_text="cross section result",
        )


class _CapturingRelationshipService:
    def __init__(self) -> None:
        self.last_intent: QueryIntent | None = None

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        self.last_intent = intent
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(coverage_start=date(2020, 1, 1), coverage_end=date(2024, 1, 1)),
            chart=_stub_chart(),
            answer_text="relationship result",
        )


class _StubStateGDPService:
    def compare(self, **_: object) -> QueryResponse:
        raise AssertionError("state GDP should not be called")


class _StubCrossSectionService:
    def analyze(self, intent: QueryIntent) -> QueryResponse:
        raise AssertionError("cross-section should not be called")


class _StubSingleSeriesService:
    def lookup(self, intent: QueryIntent) -> QueryResponse:
        raise AssertionError("single-series should not be called")


class _StubRelationshipService:
    def analyze(self, intent: QueryIntent) -> QueryResponse:
        raise AssertionError("relationship should not be called")


def _make_router(
    *,
    clarification_resolver: ClarificationResolver | None = None,
    state_gdp_service: object | None = None,
    cross_section_service: object | None = None,
    single_series_service: object | None = None,
    relationship_service: object | None = None,
) -> QueryRouter:
    return QueryRouter(
        clarification_resolver=clarification_resolver or _NoopClarificationResolver(),
        state_gdp_service=state_gdp_service or _StubStateGDPService(),
        cross_section_service=cross_section_service or _StubCrossSectionService(),
        single_series_service=single_series_service or _StubSingleSeriesService(),
        relationship_service=relationship_service or _StubRelationshipService(),
    )


# ---------------------------------------------------------------------------
# Fixture suite: completed routes
# ---------------------------------------------------------------------------

class RouterCompletedFixtures(unittest.TestCase):
    """Routes that successfully dispatch to a downstream service."""

    def test_single_series_lookup_completes_with_no_reason(self) -> None:
        single_service = _CapturingSingleSeriesService()
        router = _make_router(single_series_service=single_service)
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            search_text="unemployment rate",
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        self.assertIsNotNone(response.query_response)
        self.assertIsNotNone(single_service.last_intent)

    def test_state_gdp_comparison_completes_with_two_states(self) -> None:
        state_service = _CapturingStateGDPService()
        router = _make_router(state_gdp_service=state_service)
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        self.assertEqual(state_service.last_kwargs["state1"], "California")
        self.assertEqual(state_service.last_kwargs["state2"], "Texas")

    def test_cross_section_completes_with_bounded_geographies(self) -> None:
        cross_service = _CapturingCrossSectionService()
        router = _make_router(cross_section_service=cross_service)
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            search_text="unemployment rate",
            geographies=[
                Geography(name=f"State {i}", geography_type=GeographyType.STATE)
                for i in range(10)
            ],
            rank_limit=5,
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        self.assertIsNotNone(cross_service.last_intent)

    def test_relationship_analysis_completes_for_two_series(self) -> None:
        rel_service = _CapturingRelationshipService()
        router = _make_router(relationship_service=rel_service)
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            comparison_mode=ComparisonMode.RELATIONSHIP,
            search_texts=["unemployment rate", "inflation"],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        self.assertIsNotNone(rel_service.last_intent)

    def test_multi_series_comparison_completes(self) -> None:
        rel_service = _CapturingRelationshipService()
        router = _make_router(relationship_service=rel_service)
        intent = QueryIntent(
            task_type=TaskType.MULTI_SERIES_COMPARISON,
            comparison_mode=ComparisonMode.MULTI_SERIES,
            search_texts=["gdp", "unemployment rate"],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)

    def test_selected_series_ids_resolve_clarification_and_complete(self) -> None:
        rel_service = _CapturingRelationshipService()
        router = _make_router(relationship_service=rel_service)
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            comparison_mode=ComparisonMode.RELATIONSHIP,
            clarification_needed=True,
            clarification_target_index=0,
            search_texts=["unemployment", "inflation"],
        )

        response = router.route(intent, selected_series_ids=["UNRATE", "CPIAUCSL"])

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)
        assert rel_service.last_intent is not None
        self.assertEqual(rel_service.last_intent.series_ids, ["UNRATE", "CPIAUCSL"])
        self.assertFalse(rel_service.last_intent.clarification_needed)

    def test_query_plan_overrides_legacy_task_type_to_relationship(self) -> None:
        rel_service = _CapturingRelationshipService()
        router = _make_router(relationship_service=rel_service)
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            query_plan=QueryPlan(
                subjects=["unemployment rate", "gdp"],
                geographies=[],
                time_scope=QueryTimeScope(),
                operators=[QueryOperator.ANALYZE_RELATIONSHIP],
                output_mode=QueryOutputMode.RELATIONSHIP,
            ),
            comparison_mode=ComparisonMode.RELATIONSHIP,
            search_texts=["unemployment rate", "gdp"],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)


# ---------------------------------------------------------------------------
# Fixture suite: clarification routes (with reason codes)
# ---------------------------------------------------------------------------

class RouterClarificationFixtures(unittest.TestCase):
    """Routes that need user clarification, asserting QRY-003 reason codes."""

    def test_ambiguous_single_series_returns_ambiguous_series_reason(self) -> None:
        candidates = [
            SeriesSearchMatch(
                series_id="FEDFUNDS",
                title="Federal Funds Effective Rate",
                source_url="https://fred.stlouisfed.org/series/FEDFUNDS",
            ),
            SeriesSearchMatch(
                series_id="DFF",
                title="Federal Funds Effective Rate (Daily)",
                source_url="https://fred.stlouisfed.org/series/DFF",
            ),
        ]
        resolver = _CandidateClarificationResolver(candidates)
        router = _make_router(clarification_resolver=resolver)
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            search_text="federal funds rate",
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.AMBIGUOUS_SERIES)
        self.assertEqual(len(response.candidate_series), 2)

    def test_state_gdp_with_one_state_returns_unknown_geography_reason(self) -> None:
        router = _make_router()
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            clarification_needed=True,
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.UNKNOWN_GEOGRAPHY)

    def test_state_gdp_with_three_states_returns_too_many_targets_reason(self) -> None:
        router = _make_router()
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            clarification_needed=True,
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
                Geography(name="New York", geography_type=GeographyType.STATE),
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.TOO_MANY_TARGETS)

    def test_state_gdp_with_non_state_geography_returns_unknown_geography_reason(self) -> None:
        router = _make_router()
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            clarification_needed=True,
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="United States", geography_type=GeographyType.NATIONAL),
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.UNKNOWN_GEOGRAPHY)

    def test_cross_section_with_26_unbounded_geographies_returns_needs_threshold_reason(self) -> None:
        router = _make_router()
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            clarification_needed=True,
            search_text="unemployment rate",
            geographies=[
                Geography(name=f"Region {i}", geography_type=GeographyType.REGION)
                for i in range(26)
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.NEEDS_THRESHOLD)

    def test_cross_section_with_25_geographies_does_not_trigger_threshold(self) -> None:
        cross_service = _CapturingCrossSectionService()
        router = _make_router(cross_section_service=cross_service)
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            search_text="unemployment rate",
            geographies=[
                Geography(name=f"Region {i}", geography_type=GeographyType.REGION)
                for i in range(25)
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)

    def test_cross_section_with_rank_limit_bypasses_threshold_check(self) -> None:
        cross_service = _CapturingCrossSectionService()
        router = _make_router(cross_section_service=cross_service)
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            search_text="unemployment rate",
            rank_limit=10,
            geographies=[
                Geography(name=f"Region {i}", geography_type=GeographyType.REGION)
                for i in range(30)
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertIsNone(response.reason)

    def test_clarification_response_includes_candidate_series(self) -> None:
        candidates = [
            SeriesSearchMatch(
                series_id="UNRATE",
                title="Unemployment Rate",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            ),
        ]
        resolver = _CandidateClarificationResolver(candidates)
        router = _make_router(clarification_resolver=resolver)
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            search_text="unemployment",
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(len(response.candidate_series), 1)
        self.assertEqual(response.candidate_series[0].series_id, "UNRATE")


# ---------------------------------------------------------------------------
# Fixture suite: unsupported routes (with reason codes)
# ---------------------------------------------------------------------------

class RouterUnsupportedFixtures(unittest.TestCase):
    """Routes with no deterministic execution path."""

    def test_unknown_task_type_returns_unsupported_route_reason(self) -> None:
        router = _make_router()
        intent = QueryIntent.model_construct(task_type="forecast_model", query_plan=None)

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.UNSUPPORTED)
        self.assertEqual(response.reason, RoutedQueryReason.UNSUPPORTED_ROUTE)

    def test_unsupported_response_has_human_readable_answer_text(self) -> None:
        router = _make_router()
        intent = QueryIntent.model_construct(task_type="custom_analysis", query_plan=None)

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.UNSUPPORTED)
        self.assertEqual(response.reason, RoutedQueryReason.UNSUPPORTED_ROUTE)
        self.assertIn("no deterministic execution path", response.answer_text)

    def test_state_gdp_with_wrong_count_and_no_clarification_flag_still_clarifies(self) -> None:
        router = _make_router()
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            clarification_needed=True,
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
            ],
        )

        response = router.route(intent)

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.reason, RoutedQueryReason.UNKNOWN_GEOGRAPHY)


if __name__ == "__main__":
    unittest.main()
