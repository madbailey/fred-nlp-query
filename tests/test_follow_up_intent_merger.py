from __future__ import annotations

from datetime import datetime, timezone
import unittest

from fred_query.schemas.analysis import RoutedQueryResponse, RoutedQueryStatus
from fred_query.schemas.intent import QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import SeriesSearchMatch
from fred_query.services.follow_up_intent_merger import FollowUpIntentMerger
from fred_query.services.query_session_service import QuerySession


class _ContextParser:
    def __init__(self, intent: QueryIntent) -> None:
        self.intent = intent
        self.last_query: str | None = None
        self.last_context: dict[str, object] | None = None

    def parse(self, query: str) -> QueryIntent:
        raise AssertionError("parse should not be called when parse_with_context is available")

    def parse_with_context(self, query: str, context: dict[str, object]) -> QueryIntent:
        self.last_query = query
        self.last_context = context
        self.intent.original_query = query
        return self.intent


def _session_context() -> QuerySession:
    previous_intent = QueryIntent(
        task_type=TaskType.SINGLE_SERIES_LOOKUP,
        series_id="UNRATE",
        search_text="unemployment rate",
    )
    routed = RoutedQueryResponse(
        status=RoutedQueryStatus.NEEDS_CLARIFICATION,
        intent=previous_intent,
        answer_text="Do you mean headline or core unemployment?",
        candidate_series=[
            SeriesSearchMatch(
                series_id="UNRATE",
                title="Unemployment Rate",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            )
        ],
    )
    return QuerySession(
        session_id="session-1",
        created_at=datetime(2026, 3, 19, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 19, tzinfo=timezone.utc),
        last_query="Show unemployment.",
        last_response=routed,
    )


class FollowUpIntentMergerTest(unittest.TestCase):
    def test_parse_intent_uses_session_parser_context(self) -> None:
        parser = _ContextParser(
            QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                transform=TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE,
            )
        )
        merger = FollowUpIntentMerger(parser)

        intent = merger.parse_intent("Now make that YoY.", _session_context())

        self.assertEqual(intent.original_query, "Now make that YoY.")
        self.assertEqual(parser.last_query, "Now make that YoY.")
        assert parser.last_context is not None
        self.assertEqual(parser.last_context["previous_query"], "Show unemployment.")
        self.assertEqual(parser.last_context["previous_status"], RoutedQueryStatus.NEEDS_CLARIFICATION.value)
        self.assertEqual(
            parser.last_context["clarification_candidates"],
            [{"series_id": "UNRATE", "title": "Unemployment Rate"}],
        )


if __name__ == "__main__":
    unittest.main()
