from __future__ import annotations

import re
from dataclasses import dataclass

from fred_query.schemas.analysis import RoutedQueryStatus
from fred_query.schemas.intent import ComparisonMode, QueryIntent, TaskType, TransformType
from fred_query.services.openai_parser_service import OpenAIIntentParser
from fred_query.services.query_session_service import QuerySession


@dataclass(frozen=True, slots=True)
class SessionTarget:
    series_id: str | None = None
    search_text: str | None = None
    indicator: str | None = None


class FollowUpIntentMerger:
    _FOLLOW_UP_TOKENS = {
        "again",
        "also",
        "another",
        "instead",
        "it",
        "same",
        "that",
        "them",
        "then",
        "those",
    }
    _FOLLOW_UP_LEADING_TOKENS = {"also", "now", "then", "instead"}
    _COMPARISON_TERMS = ("compare", "comparison", "versus", "vs", "against")
    _RELATIONSHIP_TERMS = ("correlation", "correlate", "co-movement", "lead", "lag", "relationship")
    _TRANSFORM_TERMS = (
        "index",
        "level",
        "levels",
        "mom",
        "moving average",
        "normalized",
        "percent change",
        "qoq",
        "rolling",
        "standard deviation",
        "stddev",
        "volatility",
        "yoy",
        "year over year",
    )
    _LATEST_RESET_TERMS = ("current", "latest", "most recent", "now", "today")
    _ASCENDING_TERMS = ("bottom", "least", "lowest", "smallest")
    _DESCENDING_TERMS = ("highest", "largest", "most", "top")

    def __init__(self, parser: OpenAIIntentParser) -> None:
        self.parser = parser

    @staticmethod
    def _build_parser_context(session_context: QuerySession | None) -> dict[str, object] | None:
        if session_context is None or session_context.last_response is None:
            return None

        previous_response = session_context.last_response
        previous_intent = (
            previous_response.query_response.intent
            if previous_response.query_response is not None
            else previous_response.intent
        )
        resolved_series = []
        if previous_response.query_response is not None:
            resolved_series = [
                {
                    "series_id": item.series.series_id,
                    "title": item.series.title,
                    "geography": item.series.geography,
                }
                for item in previous_response.query_response.analysis.series_results
            ]

        return {
            "previous_query": session_context.last_query,
            "previous_status": previous_response.status.value,
            "previous_intent": previous_intent.model_dump(mode="json"),
            "resolved_series": resolved_series,
            "clarification_candidates": [
                {
                    "series_id": candidate.series_id,
                    "title": candidate.title,
                }
                for candidate in previous_response.candidate_series
            ],
        }

    def parse_intent(self, query: str, session_context: QuerySession | None) -> QueryIntent:
        parser_context = self._build_parser_context(session_context)
        parse_with_context = getattr(self.parser, "parse_with_context", None)
        if parser_context and callable(parse_with_context):
            return parse_with_context(query, parser_context)
        return self.parser.parse(query)

    @staticmethod
    def _session_intent(session_context: QuerySession | None) -> QueryIntent | None:
        if session_context is None or session_context.last_response is None:
            return None
        if session_context.last_response.query_response is not None:
            return session_context.last_response.query_response.intent
        return session_context.last_response.intent

    @staticmethod
    def _tokenize(text: str | None) -> list[str]:
        if not text:
            return []
        return re.findall(r"[A-Za-z0-9]+", text.lower())

    @classmethod
    def _target_count_for_intent(cls, intent: QueryIntent) -> int:
        if intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            return max(2, len(intent.series_ids), len(intent.search_texts), len(intent.indicators))
        return 1

    @classmethod
    def _extract_targets_from_intent(cls, intent: QueryIntent) -> list[SessionTarget]:
        targets: list[SessionTarget] = []
        for index in range(cls._target_count_for_intent(intent)):
            series_id = intent.series_id if index == 0 else None
            search_text = intent.search_text if index == 0 else None
            if index < len(intent.series_ids) and intent.series_ids[index]:
                series_id = intent.series_ids[index]
            if index < len(intent.search_texts) and intent.search_texts[index]:
                search_text = intent.search_texts[index]
            indicator = intent.indicators[index] if index < len(intent.indicators) else None
            if series_id or search_text or indicator:
                targets.append(
                    SessionTarget(
                        series_id=series_id,
                        search_text=search_text,
                        indicator=indicator,
                    )
                )
        return targets

    @classmethod
    def _resolved_session_targets(cls, session_context: QuerySession | None) -> list[SessionTarget]:
        intent = cls._session_intent(session_context)
        response = session_context.last_response if session_context is not None else None
        if intent is None or response is None:
            return []

        series_results = []
        if response.query_response is not None:
            series_results = response.query_response.analysis.series_results

        base_targets = cls._extract_targets_from_intent(intent)
        targets: list[SessionTarget] = []
        for index in range(max(cls._target_count_for_intent(intent), len(series_results))):
            resolved = series_results[index] if index < len(series_results) else None
            series_id = resolved.series.series_id if resolved is not None else None
            search_text = resolved.series.title if resolved is not None else None
            indicator = resolved.series.title if resolved is not None else None

            if index < len(base_targets):
                if base_targets[index].series_id:
                    series_id = base_targets[index].series_id
                if base_targets[index].search_text:
                    search_text = base_targets[index].search_text
                if base_targets[index].indicator:
                    indicator = base_targets[index].indicator

            if series_id or search_text or indicator:
                targets.append(
                    SessionTarget(
                        series_id=series_id,
                        search_text=search_text,
                        indicator=indicator,
                    )
                )
        return targets

    @classmethod
    def _query_contains_any(cls, query: str, phrases: tuple[str, ...] | set[str]) -> bool:
        lowered = query.lower()
        return any(phrase in lowered for phrase in phrases)

    @classmethod
    def _query_mentions_transform(cls, query: str) -> bool:
        return cls._query_contains_any(query, cls._TRANSFORM_TERMS)

    @classmethod
    def _query_mentions_latest_reset(cls, query: str) -> bool:
        return cls._query_contains_any(query, cls._LATEST_RESET_TERMS)

    @classmethod
    def _intent_has_subject(cls, intent: QueryIntent) -> bool:
        return bool(
            intent.series_id
            or intent.search_text
            or intent.indicators
            or intent.geographies
            or any(intent.series_ids)
            or any(intent.search_texts)
        )

    @classmethod
    def _is_follow_up_query(cls, query: str, intent: QueryIntent, session_context: QuerySession | None) -> bool:
        if session_context is None or session_context.last_response is None:
            return False

        tokens = cls._tokenize(query)
        token_set = set(tokens)
        if token_set & cls._FOLLOW_UP_TOKENS:
            return True
        if tokens and tokens[0] in cls._FOLLOW_UP_LEADING_TOKENS and len(tokens) <= 8:
            return True
        if session_context.last_response.status == RoutedQueryStatus.NEEDS_CLARIFICATION and len(tokens) <= 8:
            return True
        if not cls._intent_has_subject(intent) and len(tokens) <= 8:
            return True
        return False

    @classmethod
    def _is_comparison_follow_up(cls, query: str, intent: QueryIntent) -> bool:
        return cls._query_contains_any(query, cls._COMPARISON_TERMS) and (
            len(cls._extract_targets_from_intent(intent)) < 2 or " it " in f" {query.lower()} "
        )

    @classmethod
    def _is_relationship_query(cls, query: str) -> bool:
        return cls._query_contains_any(query, cls._RELATIONSHIP_TERMS)

    @classmethod
    def _is_ranking_follow_up(cls, query: str, current: QueryIntent, previous: QueryIntent) -> bool:
        if current.task_type == TaskType.CROSS_SECTION:
            return previous.task_type == TaskType.CROSS_SECTION
        query_text = query.lower()
        return (
            previous.task_type == TaskType.CROSS_SECTION
            and any(term in query_text for term in ("rank", "top", "bottom", "highest", "lowest"))
        )

    @classmethod
    def _apply_temporal_follow_up_overrides(
        cls,
        merged: QueryIntent,
        current: QueryIntent,
        *,
        query: str,
    ) -> QueryIntent:
        if current.start_date is not None:
            merged.start_date = current.start_date
        if current.end_date is not None:
            merged.end_date = current.end_date
        elif cls._query_mentions_latest_reset(query):
            merged.end_date = None
        if current.observation_date is not None:
            merged.observation_date = current.observation_date
        elif cls._query_mentions_latest_reset(query):
            merged.observation_date = None
        if current.frequency:
            merged.frequency = current.frequency
        return merged

    @classmethod
    def _apply_transform_follow_up_overrides(
        cls,
        merged: QueryIntent,
        current: QueryIntent,
        *,
        query: str,
    ) -> QueryIntent:
        if (
            cls._query_mentions_transform(query)
            or current.transform != TransformType.LEVEL
            or current.transform_window is not None
        ):
            merged.transform = current.transform
            merged.transform_window = current.transform_window
            merged.normalization = current.normalization
        return merged

    @staticmethod
    def _merge_parser_notes(
        previous: QueryIntent,
        current: QueryIntent,
        *,
        previous_query: str | None,
    ) -> list[str]:
        merged_notes: list[str] = []
        for note in [*previous.parser_notes, *current.parser_notes]:
            if note and note not in merged_notes:
                merged_notes.append(note)
        if previous_query:
            merged_notes.append(f"Applied follow-up session context from prior query: {previous_query}")
        return merged_notes

    @classmethod
    def _overlay_single_subject_fields(cls, merged: QueryIntent, current: QueryIntent) -> QueryIntent:
        if current.series_id:
            merged.series_id = current.series_id
        if current.search_text:
            merged.search_text = current.search_text
        if current.indicators:
            merged.indicators = current.indicators
        if current.geographies:
            merged.geographies = current.geographies
        return merged

    @classmethod
    def _overlay_cross_section_fields(cls, merged: QueryIntent, current: QueryIntent, *, query: str) -> QueryIntent:
        merged.task_type = TaskType.CROSS_SECTION
        merged.comparison_mode = ComparisonMode.CROSS_SECTION
        if current.cross_section_scope is not None:
            merged.cross_section_scope = current.cross_section_scope
        if current.rank_limit is not None:
            merged.rank_limit = current.rank_limit
        query_text = query.lower()
        if any(term in query_text for term in cls._ASCENDING_TERMS):
            merged.sort_descending = False
        elif any(term in query_text for term in cls._DESCENDING_TERMS):
            merged.sort_descending = True
        return cls._overlay_single_subject_fields(merged, current)

    @classmethod
    def _build_comparison_follow_up(
        cls,
        previous: QueryIntent,
        current: QueryIntent,
        *,
        query: str,
        previous_targets: list[SessionTarget],
        current_targets: list[SessionTarget],
    ) -> QueryIntent:
        if len(current_targets) >= 2:
            merged = current.model_copy(deep=True)
            if merged.start_date is None:
                merged.start_date = previous.start_date
            if merged.end_date is None and not cls._query_mentions_latest_reset(query):
                merged.end_date = previous.end_date
            if not merged.frequency:
                merged.frequency = previous.frequency
            return merged

        if not previous_targets or not current_targets:
            return current

        new_target = current_targets[0]
        reference_target = previous_targets[0]
        merged = previous.model_copy(deep=True)
        merged.task_type = (
            TaskType.RELATIONSHIP_ANALYSIS
            if cls._is_relationship_query(query) or current.task_type == TaskType.RELATIONSHIP_ANALYSIS
            else TaskType.MULTI_SERIES_COMPARISON
        )
        merged.comparison_mode = (
            ComparisonMode.RELATIONSHIP
            if merged.task_type == TaskType.RELATIONSHIP_ANALYSIS
            else ComparisonMode.MULTI_SERIES
        )
        merged.series_id = None
        merged.search_text = None
        merged.cross_section_scope = None
        merged.rank_limit = None
        merged.series_ids = [reference_target.series_id, new_target.series_id]
        merged.search_texts = [
            reference_target.search_text or reference_target.indicator or reference_target.series_id or "series 1",
            new_target.search_text or new_target.indicator or new_target.series_id or "series 2",
        ]
        merged.indicators = [
            reference_target.indicator or reference_target.search_text or reference_target.series_id or "series 1",
            new_target.indicator or new_target.search_text or new_target.series_id or "series 2",
        ]
        return merged

    def merge(
        self,
        query: str,
        current: QueryIntent,
        session_context: QuerySession | None,
    ) -> QueryIntent:
        previous = self._session_intent(session_context)
        if previous is None or not self._is_follow_up_query(query, current, session_context):
            return current.refresh_query_plan()

        previous_targets = self._resolved_session_targets(session_context)
        current_targets = self._extract_targets_from_intent(current)

        if self._is_comparison_follow_up(query, current):
            merged = self._build_comparison_follow_up(
                previous,
                current,
                query=query,
                previous_targets=previous_targets,
                current_targets=current_targets,
            )
        elif self._is_ranking_follow_up(query, current, previous):
            merged = self._overlay_cross_section_fields(previous.model_copy(deep=True), current, query=query)
        else:
            merged = previous.model_copy(deep=True)
            if current.task_type == TaskType.CROSS_SECTION:
                merged = self._overlay_cross_section_fields(merged, current, query=query)
            elif current.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS) and current_targets:
                merged.task_type = current.task_type
                merged.comparison_mode = current.comparison_mode
                if current.search_texts:
                    merged.search_texts = current.search_texts
                if current.series_ids:
                    merged.series_ids = current.series_ids
                if current.indicators:
                    merged.indicators = current.indicators
            else:
                if current.task_type != previous.task_type and self._intent_has_subject(current):
                    merged.task_type = current.task_type
                    merged.comparison_mode = current.comparison_mode
                merged = self._overlay_single_subject_fields(merged, current)

        merged = self._apply_temporal_follow_up_overrides(merged, current, query=query)
        merged = self._apply_transform_follow_up_overrides(merged, current, query=query)
        if current.units_preference:
            merged.units_preference = current.units_preference
        if current.transform_window is not None:
            merged.transform_window = current.transform_window
        if current.geographies:
            merged.geographies = current.geographies
        merged.original_query = query
        merged.clarification_needed = current.clarification_needed
        merged.clarification_question = current.clarification_question
        merged.clarification_target_index = current.clarification_target_index
        merged.parser_notes = self._merge_parser_notes(
            previous,
            current,
            previous_query=session_context.last_query if session_context is not None else None,
        )
        return merged.refresh_query_plan()
