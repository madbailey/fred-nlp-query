from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import QueryResponse, SeriesAnalysis
from fred_query.schemas.intent import CrossSectionScope, QueryIntent, TaskType, TransformType

_MAX_SUGGESTIONS = 3
_SUBJECT_CANDIDATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "inflation",
        (
            "inflation",
            "consumer price index",
            "cpi",
            "pce",
            "price index",
            "deflator",
        ),
    ),
    (
        "unemployment",
        (
            "unemployment",
            "jobless",
            "labor force",
            "unrate",
        ),
    ),
    (
        "the federal funds rate",
        (
            "federal funds",
            "fed funds",
            "fedfunds",
            "sofr",
            "treasury",
            "yield",
            "mortgage",
        ),
    ),
    (
        "oil prices",
        (
            "oil",
            "brent",
            "wti",
            "crude",
        ),
    ),
)


def build_follow_up_suggestions(response: QueryResponse) -> list[str]:
    prompts: list[str] = []
    intent = response.intent

    if intent.task_type == TaskType.SINGLE_SERIES_LOOKUP:
        _append_prompt(prompts, _single_series_compare_prompt(response))
        _append_prompt(prompts, _single_series_transform_prompt(intent))
        _append_prompt(prompts, _single_series_peak_prompt(response))
        _append_prompt(prompts, _extend_prompt(intent, response.analysis.coverage_start))
        _append_prompt(prompts, _recent_focus_prompt(intent, response.analysis.coverage_start, response.analysis.coverage_end))
        _append_prompt(prompts, _latest_prompt(intent, task_type=intent.task_type))
        return prompts[:_MAX_SUGGESTIONS]

    if intent.task_type == TaskType.CROSS_SECTION:
        _append_prompt(prompts, _cross_section_flip_prompt(intent, response))
        _append_prompt(prompts, _cross_section_limit_prompt(intent))
        _append_prompt(prompts, _cross_section_states_prompt(intent, response))
        _append_prompt(prompts, _latest_prompt(intent, task_type=intent.task_type))
        return prompts[:_MAX_SUGGESTIONS]

    if intent.task_type == TaskType.STATE_GDP_COMPARISON:
        _append_prompt(prompts, _state_gdp_normalization_prompt(intent))
        _append_prompt(prompts, _extend_prompt(intent, response.analysis.coverage_start))
        _append_prompt(prompts, _recent_focus_prompt(intent, response.analysis.coverage_start, response.analysis.coverage_end))
        _append_prompt(prompts, _latest_prompt(intent, task_type=intent.task_type))
        return prompts[:_MAX_SUGGESTIONS]

    if intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
        _append_prompt(prompts, _comparison_swap_prompt(response))
        _append_prompt(prompts, _extend_prompt(intent, response.analysis.coverage_start))
        _append_prompt(prompts, _recent_focus_prompt(intent, response.analysis.coverage_start, response.analysis.coverage_end))
        _append_prompt(prompts, _latest_prompt(intent, task_type=intent.task_type))
        return prompts[:_MAX_SUGGESTIONS]

    return []


def _append_prompt(prompts: list[str], prompt: str | None) -> None:
    normalized = (prompt or "").strip()
    if normalized and normalized not in prompts:
        prompts.append(normalized)


def _series_text(result: SeriesAnalysis) -> str:
    series = result.series
    return " ".join(
        value
        for value in (
            series.series_id,
            series.title,
            series.indicator,
            series.units,
            series.geography,
        )
        if value
    ).lower()


def _series_matches_keywords(result: SeriesAnalysis, keywords: tuple[str, ...]) -> bool:
    text = _series_text(result)
    return any(keyword in text for keyword in keywords)


def _suggest_alternative_subject(series_results: list[SeriesAnalysis]) -> str | None:
    if not series_results:
        return None

    for label, keywords in _SUBJECT_CANDIDATES:
        if not any(_series_matches_keywords(result, keywords) for result in series_results):
            return label
    return None


def _single_series_compare_prompt(response: QueryResponse) -> str | None:
    subject = _suggest_alternative_subject(response.analysis.series_results[:1])
    if subject is None:
        return None
    return f"How does this compare to {subject} over the same period?"


def _single_series_transform_prompt(intent: QueryIntent) -> str:
    if intent.transform != TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE:
        return "Show this as year-over-year change"
    if intent.transform != TransformType.ROLLING_AVERAGE:
        return "Try a rolling average instead"
    if intent.transform != TransformType.NORMALIZED_INDEX and not intent.normalization:
        return "Normalize this to an index starting at 100"
    return "Show this in reported levels instead"


def _single_series_peak_prompt(response: QueryResponse) -> str | None:
    if not response.analysis.series_results:
        return None

    context = response.analysis.series_results[0].historical_context
    if context is None or context.max_date is None:
        return None
    return "What was the peak over this period?"


def _comparison_swap_prompt(response: QueryResponse) -> str | None:
    subject = _suggest_alternative_subject(response.analysis.series_results)
    if subject is None:
        return None
    return f"Compare it to {subject} instead"


def _cross_section_flip_prompt(intent: QueryIntent, response: QueryResponse) -> str:
    limit = _cross_section_display_limit(intent, response)
    direction = "bottom" if intent.sort_descending else "top"
    scope = intent.cross_section_scope or CrossSectionScope.SINGLE_SERIES
    suffix = " states" if scope == CrossSectionScope.SINGLE_SERIES else ""
    return f"Rank the {direction} {limit}{suffix} instead"


def _cross_section_limit_prompt(intent: QueryIntent) -> str | None:
    scope = intent.cross_section_scope or CrossSectionScope.SINGLE_SERIES
    direction = "top" if intent.sort_descending else "bottom"
    if scope == CrossSectionScope.SINGLE_SERIES:
        return f"Rank the {direction} 10 states by this indicator"

    current_limit = intent.rank_limit or 10
    alternate_limit = 5 if current_limit != 5 else 10
    return f"Rank the {direction} {alternate_limit} instead"


def _cross_section_states_prompt(intent: QueryIntent, response: QueryResponse) -> str | None:
    scope = intent.cross_section_scope or CrossSectionScope.SINGLE_SERIES
    if scope == CrossSectionScope.STATES:
        return None
    if len(response.analysis.series_results) >= 2:
        return "Use the latest available observation instead" if intent.observation_date else None
    return "Rank all states by this indicator"


def _cross_section_display_limit(intent: QueryIntent, response: QueryResponse) -> int:
    if intent.rank_limit is not None:
        return intent.rank_limit
    result_count = len(response.analysis.series_results)
    if result_count <= 0:
        return 10
    return min(result_count, 10)


def _state_gdp_normalization_prompt(intent: QueryIntent) -> str:
    if intent.normalization or intent.transform == TransformType.NORMALIZED_INDEX:
        return "Show this in reported GDP levels instead"
    return "Normalize both states to 100 at the start"


def _extend_prompt(intent: QueryIntent, coverage_start: date | None) -> str | None:
    current_start = intent.start_date or coverage_start
    if current_start is None:
        return None

    anchor_year = _extend_anchor_year(current_start.year)
    if anchor_year is None or current_start.year <= anchor_year:
        return None
    return f"Extend this back to {anchor_year}"


def _extend_anchor_year(current_year: int) -> int | None:
    if current_year >= 2022:
        return 2020
    if current_year >= 2005:
        return 2000
    if current_year >= 1995:
        return 1990
    return None


def _recent_focus_prompt(
    intent: QueryIntent,
    coverage_start: date | None,
    coverage_end: date | None,
) -> str | None:
    current_start = intent.start_date or coverage_start
    current_end = intent.end_date or coverage_end
    if current_start is None or current_end is None:
        return None
    if current_start.year >= 2020:
        return None
    if current_end.year - current_start.year < 8:
        return None
    return "Focus on the period since 2020 instead"


def _latest_prompt(intent: QueryIntent, *, task_type: TaskType) -> str | None:
    if task_type == TaskType.CROSS_SECTION:
        if intent.observation_date is not None or intent.end_date is not None:
            return "Use the latest available observation instead"
        return None

    if intent.end_date is not None:
        return "Use the latest available data instead"
    return None
