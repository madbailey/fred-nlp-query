from __future__ import annotations

from importlib import import_module

_EXPORTS: dict[str, tuple[str, str]] = {
    "AnswerService": ("fred_query.services.answer_service", "AnswerService"),
    "ChartService": ("fred_query.services.chart_service", "ChartService"),
    "ClarificationResolver": ("fred_query.services.clarification_resolver", "ClarificationResolver"),
    "CrossSectionService": ("fred_query.services.cross_section_service", "CrossSectionService"),
    "FREDAPIError": ("fred_query.services.fred_client", "FREDAPIError"),
    "FREDClient": ("fred_query.services.fred_client", "FREDClient"),
    "FollowUpIntentMerger": ("fred_query.services.follow_up_intent_merger", "FollowUpIntentMerger"),
    "IntentService": ("fred_query.services.intent_service", "IntentService"),
    "NaturalLanguageQueryService": (
        "fred_query.services.natural_language_query_service",
        "NaturalLanguageQueryService",
    ),
    "OpenAIIntentParser": ("fred_query.services.openai_parser_service", "OpenAIIntentParser"),
    "QueryRouter": ("fred_query.services.query_router", "QueryRouter"),
    "QuerySession": ("fred_query.services.query_session_service", "QuerySession"),
    "QuerySessionService": ("fred_query.services.query_session_service", "QuerySessionService"),
    "RelationshipAnalysisService": ("fred_query.services.relationship_service", "RelationshipAnalysisService"),
    "ResolverService": ("fred_query.services.resolver_service", "ResolverService"),
    "SingleSeriesLookupService": ("fred_query.services.single_series_service", "SingleSeriesLookupService"),
    "StateGDPComparisonService": ("fred_query.services.comparison_service", "StateGDPComparisonService"),
    "TransformService": ("fred_query.services.transform_service", "TransformService"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> object:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:  # pragma: no cover
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
