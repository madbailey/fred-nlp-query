from __future__ import annotations

from openai import OpenAI

from fred_query.errors import ConfigurationError, IntentParsingError
from fred_query.schemas.intent import CrossSectionScope, QueryIntent, TaskType
from fred_query.services.cross_section_intent_service import CrossSectionIntentService


PARSER_INSTRUCTIONS = """You convert natural-language economic questions into a strict QueryIntent.

Supported task types:
- state_gdp_comparison: the user compares GDP or economic size/growth between two US states
- cross_section: the user asks for a latest or point-in-time snapshot, ranking, highest/lowest value, or a specific date's value rather than a time-series trend
- single_series_lookup: the user asks for one economic indicator, one FRED series, or mentions a specific FRED series ID
- multi_series_comparison: the user compares two non-state-GDP series
- relationship_analysis: the user asks about correlation, co-movement, lead-lag behavior, or the relationship between two series

Rules:
- Prefer clarification over guessing when the request is ambiguous.
- Set clarification_needed=true and provide clarification_question when the request could map to multiple materially different FRED series.
- When clarification_needed=true for a single series, set clarification_target_index=0.
- When clarification_needed=true for a relationship or multi-series question, set clarification_target_index to the 0-based index of the ambiguous series target.
- If the user explicitly mentions a FRED series ID, copy it into series_id and use task_type=single_series_lookup.
- Use cross_section when the user asks for the latest or a specific date's value, asks which geography has the highest or lowest value, or asks to rank geographies at a point in time.
- For cross_section queries that rank all US states, set cross_section_scope=states.
- For cross_section queries that compare a named set of geographies, set cross_section_scope=provided_geographies and populate geographies.
- For cross_section queries that only need one series at one date, set cross_section_scope=single_series.
- For cross_section ranking queries, set rank_limit when the user explicitly asks for top N or bottom N.
- For cross_section ranking queries, set sort_descending=false for lowest/bottom/least queries.
- For cross_section queries with a specific point in time, populate observation_date.
- For relationship_analysis and multi_series_comparison, populate search_texts with one short FRED-friendly phrase per series target in the same order they appear in the question.
- For relationship_analysis and multi_series_comparison, if the user explicitly mentions series IDs, put them in series_ids in the same order as the targets.
- Populate search_text with a short FRED-friendly search phrase whenever series_id is not provided.
- Use normalization=true only when the user is asking for relative growth, indexed comparison, or wants the series normalized.
- Preserve date ranges when the user gives them. If no dates are given, leave them null.
- For state_gdp_comparison, include exactly two state geographies when possible.
- For relationship_analysis and multi_series_comparison, prefer exactly two targets. If the request names fewer or more than two meaningful targets, set clarification_needed=true.
- For unsupported or underspecified requests, still return the closest task_type but set clarification_needed=true.
- parser_notes should be short factual notes about assumptions or unresolved ambiguity.
"""


class OpenAIIntentParser:
    """Parse natural-language queries into a strict QueryIntent."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-5.4-mini",
        reasoning_effort: str = "low",
        client: OpenAI | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ConfigurationError("An OpenAI API key is required for intent parsing.")

        self.model = model
        self.reasoning_effort = reasoning_effort
        self.client = client or OpenAI(api_key=api_key)

    def parse(self, query: str) -> QueryIntent:
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=PARSER_INSTRUCTIONS,
                input=query,
                text_format=QueryIntent,
                reasoning={"effort": self.reasoning_effort},
                store=False,
            )
        except Exception as exc:
            raise IntentParsingError(f"Natural-language parsing failed: {exc}") from exc

        intent = response.output_parsed
        if intent is None:
            raise IntentParsingError("OpenAI parser returned no structured intent.")

        if not intent.original_query:
            intent.original_query = query

        if intent.task_type == TaskType.STATE_GDP_COMPARISON and len(intent.geographies) != 2:
            intent.clarification_needed = True
            intent.clarification_question = (
                intent.clarification_question
                or "Which two US states do you want to compare for GDP?"
            )

        if (
            intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS)
            and len(intent.search_texts) + len([value for value in intent.series_ids if value]) < 2
        ):
            intent.clarification_needed = True
            intent.clarification_question = (
                intent.clarification_question
                or "Which two economic series do you want to analyze together?"
            )

        if intent.task_type == TaskType.SINGLE_SERIES_LOOKUP and intent.clarification_needed:
            intent.clarification_target_index = 0
        if (
            intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS)
            and intent.clarification_needed
            and intent.clarification_target_index is None
        ):
            intent.clarification_target_index = 0

        CrossSectionIntentService.promote_task_type(intent, query=query)

        if intent.task_type == TaskType.CROSS_SECTION:
            CrossSectionIntentService.apply_defaults(intent, query=query)

            if (
                not intent.series_id
                and not intent.search_text
                and not intent.indicators
            ):
                intent.clarification_needed = True
                intent.clarification_question = (
                    intent.clarification_question
                    or "Which economic indicator should I rank or look up for that cross-section query?"
                )

            if (
                intent.cross_section_scope == CrossSectionScope.PROVIDED_GEOGRAPHIES
                and not intent.geographies
            ):
                intent.clarification_needed = True
                intent.clarification_question = (
                    intent.clarification_question
                    or "Which geographies do you want included in the cross-section?"
                )

        return intent
