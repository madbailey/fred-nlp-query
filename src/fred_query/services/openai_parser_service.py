from __future__ import annotations

from openai import OpenAI

from fred_query.errors import ConfigurationError, IntentParsingError
from fred_query.schemas.intent import QueryIntent, TaskType


PARSER_INSTRUCTIONS = """You convert natural-language economic questions into a strict QueryIntent.

Supported task types:
- state_gdp_comparison: the user compares GDP or economic size/growth between two US states
- single_series_lookup: the user asks for one economic indicator, one FRED series, or mentions a specific FRED series ID
- multi_series_comparison: the user compares multiple non-state-GDP series

Rules:
- Prefer clarification over guessing when the request is ambiguous.
- Set clarification_needed=true and provide clarification_question when the request could map to multiple materially different FRED series.
- If the user explicitly mentions a FRED series ID, copy it into series_id and use task_type=single_series_lookup.
- Populate search_text with a short FRED-friendly search phrase whenever series_id is not provided.
- Use normalization=true only when the user is asking for relative growth, indexed comparison, or wants the series normalized.
- Preserve date ranges when the user gives them. If no dates are given, leave them null.
- For state_gdp_comparison, include exactly two state geographies when possible.
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

        return intent
