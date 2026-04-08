from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import RoutedQueryReason, RoutedQueryResponse, RoutedQueryStatus
from fred_query.schemas.intent import GeographyType, QueryIntent, TaskType
from fred_query.services.clarification_resolver import ClarificationResolver
from fred_query.services.comparison_service import StateGDPComparisonService
from fred_query.services.cross_section_service import CrossSectionService
from fred_query.services.relationship_service import RelationshipAnalysisService
from fred_query.services.single_series_service import SingleSeriesLookupService


class QueryRouter:
    def __init__(
        self,
        *,
        clarification_resolver: ClarificationResolver,
        state_gdp_service: StateGDPComparisonService,
        cross_section_service: CrossSectionService,
        single_series_service: SingleSeriesLookupService,
        relationship_service: RelationshipAnalysisService,
    ) -> None:
        self.clarification_resolver = clarification_resolver
        self.state_gdp_service = state_gdp_service
        self.cross_section_service = cross_section_service
        self.single_series_service = single_series_service
        self.relationship_service = relationship_service

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @staticmethod
    def _clarification_reason(intent: QueryIntent) -> RoutedQueryReason:
        if intent.task_type == TaskType.STATE_GDP_COMPARISON or intent.planned_task_type == TaskType.STATE_GDP_COMPARISON:
            if len(intent.geographies) > 2:
                return RoutedQueryReason.TOO_MANY_TARGETS
            if (
                len(intent.geographies) < 2
                or any(item.geography_type not in (GeographyType.STATE,) for item in intent.geographies)
            ):
                return RoutedQueryReason.UNKNOWN_GEOGRAPHY
        return RoutedQueryReason.AMBIGUOUS_SERIES

    @staticmethod
    def _unsupported_reason(intent: QueryIntent) -> RoutedQueryReason:
        if intent.planned_task_type == TaskType.CROSS_SECTION and intent.rank_limit is None and len(intent.geographies) > 25:
            return RoutedQueryReason.NEEDS_THRESHOLD
        return RoutedQueryReason.UNSUPPORTED_ROUTE

    @staticmethod
    def apply_selected_series(intent: QueryIntent, selected_series_ids: list[str | None] | None) -> QueryIntent:
        if not selected_series_ids:
            return intent

        normalized_ids = list(selected_series_ids)
        if intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            target_count = max(2, len(intent.search_texts), len(intent.series_ids), len(normalized_ids))
            intent.series_ids = (intent.series_ids + [None] * target_count)[:target_count]
            for index, series_id in enumerate(normalized_ids):
                if index >= len(intent.series_ids) or not series_id:
                    continue
                intent.series_ids[index] = series_id
                intent.parser_notes.append(
                    f"User selected explicit series ID {series_id} for target {index} from clarification options."
                )
            intent.clarification_needed = False
            intent.clarification_question = None
            intent.clarification_target_index = None
            return intent.refresh_query_plan()

        selected_series_id = next((value for value in normalized_ids if value), None)
        if selected_series_id:
            intent.task_type = TaskType.SINGLE_SERIES_LOOKUP
            intent.series_id = selected_series_id
            intent.clarification_needed = False
            intent.clarification_question = None
            intent.clarification_target_index = None
            intent.parser_notes.append(
                f"User selected explicit series ID {selected_series_id} from clarification options."
            )
        return intent.refresh_query_plan()

    def route(
        self,
        intent: QueryIntent,
        *,
        selected_series_ids: list[str | None] | None = None,
    ) -> RoutedQueryResponse:
        intent = self.apply_selected_series(intent, selected_series_ids)
        task_type = intent.planned_task_type

        if intent.clarification_needed:
            candidate_series = self.clarification_resolver.build_candidates(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.NEEDS_CLARIFICATION,
                reason=self._clarification_reason(intent),
                intent=intent,
                answer_text=self.clarification_resolver.answer_text(intent, candidate_series=candidate_series),
                candidate_series=candidate_series,
            )

        if task_type == TaskType.STATE_GDP_COMPARISON:
            if len(intent.geographies) != 2:
                return RoutedQueryResponse(
                    status=RoutedQueryStatus.NEEDS_CLARIFICATION,
                    reason=self._clarification_reason(intent),
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
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if task_type == TaskType.SINGLE_SERIES_LOOKUP:
            query_response = self.single_series_service.lookup(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if task_type == TaskType.CROSS_SECTION:
            query_response = self.cross_section_service.analyze(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            query_response = self.relationship_service.analyze(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        return RoutedQueryResponse(
            status=RoutedQueryStatus.UNSUPPORTED,
            reason=self._unsupported_reason(intent),
            intent=intent,
            answer_text=(
                "The parser understood the request, but there is no deterministic execution path for it yet. "
                "Right now the live implementation supports state GDP comparisons, point-in-time cross sections, "
                "single-series lookups, and pairwise non-state relationship analysis."
            ),
        )
