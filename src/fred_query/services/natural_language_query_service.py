from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import RoutedQueryResponse, RoutedQueryStatus
from fred_query.schemas.intent import TaskType
from fred_query.services.comparison_service import StateGDPComparisonService
from fred_query.services.fred_client import FREDClient
from fred_query.services.openai_parser_service import OpenAIIntentParser
from fred_query.services.single_series_service import SingleSeriesLookupService


class NaturalLanguageQueryService:
    """Route a natural-language query into deterministic execution."""

    def __init__(
        self,
        *,
        parser: OpenAIIntentParser,
        fred_client: FREDClient,
        state_gdp_service: StateGDPComparisonService | None = None,
        single_series_service: SingleSeriesLookupService | None = None,
    ) -> None:
        self.parser = parser
        self.fred_client = fred_client
        self.state_gdp_service = state_gdp_service or StateGDPComparisonService(fred_client)
        self.single_series_service = single_series_service or SingleSeriesLookupService(fred_client)

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @staticmethod
    def _apply_selected_series(intent, selected_series_id: str | None):
        if not selected_series_id:
            return intent

        intent.task_type = TaskType.SINGLE_SERIES_LOOKUP
        intent.series_id = selected_series_id
        intent.clarification_needed = False
        intent.clarification_question = None
        intent.parser_notes.append(
            f"User selected explicit series ID {selected_series_id} from clarification options."
        )
        return intent

    def ask(self, query: str, *, selected_series_id: str | None = None) -> RoutedQueryResponse:
        intent = self._apply_selected_series(
            self.parser.parse(query),
            selected_series_id,
        )

        if intent.clarification_needed:
            candidates = []
            if intent.search_text:
                try:
                    candidates = self.fred_client.search_series(intent.search_text, limit=5)
                except Exception:
                    candidates = []

            return RoutedQueryResponse(
                status=RoutedQueryStatus.NEEDS_CLARIFICATION,
                intent=intent,
                answer_text=intent.clarification_question or "I need one clarification before I can query FRED safely.",
                candidate_series=candidates,
            )

        if intent.task_type == TaskType.STATE_GDP_COMPARISON:
            if len(intent.geographies) != 2:
                return RoutedQueryResponse(
                    status=RoutedQueryStatus.NEEDS_CLARIFICATION,
                    intent=intent,
                    answer_text="I need exactly two US states to run the GDP comparison.",
                )

            query_response = self.state_gdp_service.compare(
                state1=intent.geographies[0].name,
                state2=intent.geographies[1].name,
                start_date=intent.start_date or self._default_start_date(),
                end_date=intent.end_date,
                normalize=intent.normalization,
            )
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if intent.task_type == TaskType.SINGLE_SERIES_LOOKUP:
            query_response = self.single_series_service.lookup(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        return RoutedQueryResponse(
            status=RoutedQueryStatus.UNSUPPORTED,
            intent=intent,
            answer_text=(
                "The parser understood the request, but there is no deterministic execution path for it yet. "
                "Right now the live implementation supports state GDP comparisons and single-series lookups."
            ),
        )
