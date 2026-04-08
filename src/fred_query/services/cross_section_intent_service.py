from __future__ import annotations

import re

from fred_query.schemas.intent import CrossSectionScope, QueryIntent, TaskType


class CrossSectionIntentService:
    """Shared cross-section intent guardrails used by parsing and execution."""

    _RANKING_TERMS = ("highest", "lowest", "top", "bottom", "rank")
    _ASCENDING_TERMS = ("lowest", "bottom", "least", "smallest")
    _NUMBER_WORDS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
    }

    @classmethod
    def _query_text(cls, intent: QueryIntent, query: str | None) -> str:
        return (query or intent.original_query or "").lower()

    @classmethod
    def is_ranking_query(cls, intent: QueryIntent, *, query: str | None = None) -> bool:
        return any(term in cls._query_text(intent, query) for term in cls._RANKING_TERMS)

    @classmethod
    def _parse_count(cls, raw_value: str) -> int | None:
        if raw_value.isdigit():
            return int(raw_value)
        return cls._NUMBER_WORDS.get(raw_value)

    @classmethod
    def explicit_rank_limit(cls, intent: QueryIntent, *, query: str | None = None) -> int | None:
        query_text = cls._query_text(intent, query)
        match = re.search(
            r"\b(?:top|bottom)\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b",
            query_text,
        )
        if match is None:
            return None
        return cls._parse_count(match.group("count"))

    @classmethod
    def display_limit_details(
        cls,
        intent: QueryIntent,
        *,
        scope: CrossSectionScope,
        result_count: int,
        query: str | None = None,
    ) -> tuple[int, str]:
        explicit_limit = cls.explicit_rank_limit(intent, query=query)
        if explicit_limit is not None:
            return min(explicit_limit, result_count), "explicit_request"

        if intent.rank_limit is not None and intent.rank_limit > 1:
            return min(intent.rank_limit, result_count), "explicit_request"

        if scope == CrossSectionScope.STATES and result_count > 10:
            return 10, "comparison_context"

        if intent.rank_limit is not None:
            return min(intent.rank_limit, result_count), "explicit_request"

        return result_count, "all_series"

    @classmethod
    def infer_scope(cls, intent: QueryIntent, *, query: str | None = None) -> CrossSectionScope:
        if intent.cross_section_scope is not None:
            return intent.cross_section_scope
        if intent.geographies:
            return CrossSectionScope.PROVIDED_GEOGRAPHIES
        if "state" in cls._query_text(intent, query):
            return CrossSectionScope.STATES
        return CrossSectionScope.SINGLE_SERIES

    @classmethod
    def apply_defaults(cls, intent: QueryIntent, *, query: str | None = None) -> QueryIntent:
        intent.cross_section_scope = cls.infer_scope(intent, query=query)
        if any(term in cls._query_text(intent, query) for term in cls._ASCENDING_TERMS):
            intent.sort_descending = False
        return intent.refresh_query_plan()

    @classmethod
    def promote_task_type(cls, intent: QueryIntent, *, query: str | None = None) -> QueryIntent:
        query_text = cls._query_text(intent, query)
        if intent.task_type == TaskType.SINGLE_SERIES_LOOKUP and intent.observation_date is not None:
            intent.task_type = TaskType.CROSS_SECTION
            intent.cross_section_scope = CrossSectionScope.SINGLE_SERIES
        if (
            intent.task_type == TaskType.STATE_GDP_COMPARISON
            and any(term in query_text for term in cls._RANKING_TERMS)
            and "state" in query_text
        ):
            intent.task_type = TaskType.CROSS_SECTION
            intent.cross_section_scope = CrossSectionScope.STATES
        return intent.refresh_query_plan()
