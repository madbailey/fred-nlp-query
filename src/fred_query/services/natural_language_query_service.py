from __future__ import annotations

from fred_query.schemas.analysis import RoutedQueryResponse
from fred_query.services.clarification_resolver import ClarificationResolver
from fred_query.services.comparison_service import StateGDPComparisonService
from fred_query.services.cross_section_service import CrossSectionService
from fred_query.services.fred_client import FREDClient
from fred_query.services.follow_up_intent_merger import FollowUpIntentMerger
from fred_query.services.openai_parser_service import OpenAIIntentParser
from fred_query.services.query_router import QueryRouter
from fred_query.services.query_session_service import QuerySession
from fred_query.services.relationship_service import RelationshipAnalysisService
from fred_query.services.single_series_service import SingleSeriesLookupService


class NaturalLanguageQueryService:
    """Route a natural-language query into deterministic execution."""

    def __init__(
        self,
        *,
        parser: OpenAIIntentParser,
        fred_client: FREDClient,
        state_gdp_service: StateGDPComparisonService | None = None,
        cross_section_service: CrossSectionService | None = None,
        single_series_service: SingleSeriesLookupService | None = None,
        relationship_service: RelationshipAnalysisService | None = None,
    ) -> None:
        self.parser = parser
        self.fred_client = fred_client
        self.state_gdp_service = state_gdp_service or StateGDPComparisonService(fred_client)
        self.cross_section_service = cross_section_service or CrossSectionService(fred_client)
        self.single_series_service = single_series_service or SingleSeriesLookupService(fred_client)
        self.relationship_service = relationship_service or RelationshipAnalysisService(fred_client)

        self.clarification_resolver = ClarificationResolver(fred_client)
        self.follow_up_intent_merger = FollowUpIntentMerger(parser)
        self.query_router = QueryRouter(
            clarification_resolver=self.clarification_resolver,
            state_gdp_service=self.state_gdp_service,
            cross_section_service=self.cross_section_service,
            single_series_service=self.single_series_service,
            relationship_service=self.relationship_service,
        )

    def ask(
        self,
        query: str,
        *,
        selected_series_id: str | None = None,
        selected_series_ids: list[str | None] | None = None,
        session_context: QuerySession | None = None,
    ) -> RoutedQueryResponse:
        effective_selected_series_ids = selected_series_ids
        if effective_selected_series_ids is None and selected_series_id is not None:
            effective_selected_series_ids = [selected_series_id]

        intent = self.follow_up_intent_merger.parse_intent(query, session_context)
        intent = self.follow_up_intent_merger.merge(query, intent, session_context)
        return self.query_router.route(intent, selected_series_ids=effective_selected_series_ids)
