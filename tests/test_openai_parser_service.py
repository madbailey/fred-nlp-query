from __future__ import annotations

from datetime import date
from types import SimpleNamespace
import unittest

from fred_query.schemas.intent import ComparisonMode, Geography, GeographyType, QueryIntent, TaskType, TransformType
from fred_query.services.openai_parser_service import OpenAIIntentParser


class _FakeResponsesAPI:
    def __init__(self, intent: QueryIntent) -> None:
        self.intent = intent

    def parse(self, **_: object) -> object:
        return SimpleNamespace(output_parsed=self.intent)


class _FakeOpenAIClient:
    def __init__(self, intent: QueryIntent) -> None:
        self.responses = _FakeResponsesAPI(intent)


class OpenAIIntentParserTest(unittest.TestCase):
    def test_parser_returns_intent_and_sets_original_query(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
            ],
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            start_date=date(2019, 1, 1),
            transform=TransformType.NORMALIZED_INDEX,
            normalization=True,
        )
        parser = OpenAIIntentParser(
            api_key="test-key",
            client=_FakeOpenAIClient(intent),
        )

        parsed = parser.parse("Compare California and Texas GDP since 2019")

        self.assertEqual(parsed.task_type, TaskType.STATE_GDP_COMPARISON)
        self.assertEqual(parsed.original_query, "Compare California and Texas GDP since 2019")

    def test_parser_requests_clarification_for_incomplete_state_gdp_intent(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            geographies=[Geography(name="California", geography_type=GeographyType.STATE)],
        )
        parser = OpenAIIntentParser(
            api_key="test-key",
            client=_FakeOpenAIClient(intent),
        )

        parsed = parser.parse("Compare California GDP")

        self.assertTrue(parsed.clarification_needed)
        self.assertIn("two US states", parsed.clarification_question or "")

    def test_relationship_parser_defaults_clarification_target_index(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            clarification_needed=True,
            clarification_question="Which inflation measure do you mean?",
            search_texts=["brent crude oil price", "inflation united states"],
        )
        parser = OpenAIIntentParser(
            api_key="test-key",
            client=_FakeOpenAIClient(intent),
        )

        parsed = parser.parse("What is the relationship between Brent crude and inflation?")

        self.assertTrue(parsed.clarification_needed)
        self.assertEqual(parsed.clarification_target_index, 0)


if __name__ == "__main__":
    unittest.main()
