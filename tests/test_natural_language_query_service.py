from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import AnalysisResult, QueryResponse, RoutedQueryStatus
from fred_query.schemas.chart import AxisSpec, ChartSpec, ChartTrace
from fred_query.schemas.intent import ComparisonMode, Geography, GeographyType, QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesSearchMatch
from fred_query.services.natural_language_query_service import NaturalLanguageQueryService


class _FakeParser:
    def __init__(self, intent: QueryIntent) -> None:
        self.intent = intent

    def parse(self, query: str) -> QueryIntent:
        self.intent.original_query = query
        return self.intent


class _FailingParser:
    def parse(self, query: str) -> QueryIntent:
        raise RuntimeError("insufficient_quota")


class _FakeFREDClient:
    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="UNRATE",
                title="Unemployment Rate",
                units="Percent",
                frequency="M",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            )
        ]


class _FakeStateGDPService:
    def compare(self, **_: object) -> QueryResponse:
        series = ResolvedSeries(
            series_id="CARGSP",
            title="Real GDP: California",
            geography="California",
            indicator="real_gdp",
            units="Millions of Chained 2017 Dollars",
            frequency="A",
            resolution_reason="fixture",
            source_url="https://fred.stlouisfed.org/series/CARGSP",
        )
        return QueryResponse(
            intent=QueryIntent(task_type=TaskType.STATE_GDP_COMPARISON),
            analysis=AnalysisResult(
                coverage_start=date(2019, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                title="Real GDP Comparison: California vs Texas",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Index"),
                series=[ChartTrace(name="California")],
                source_note="Source: FRED, Federal Reserve Bank of St. Louis",
            ),
            answer_text="Completed comparison.",
        )


class _FakeSingleSeriesService:
    def lookup(self, intent: QueryIntent) -> QueryResponse:
        series = ResolvedSeries(
            series_id="UNRATE",
            title="Unemployment Rate",
            geography="United States",
            indicator="unemployment_rate",
            units="Percent",
            frequency="M",
            resolution_reason="fixture",
            source_url="https://fred.stlouisfed.org/series/UNRATE",
        )
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(
                coverage_start=date(2020, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                title="Unemployment Rate",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Percent"),
                series=[ChartTrace(name="UNRATE")],
                source_note="Source: FRED, Federal Reserve Bank of St. Louis",
            ),
            answer_text="Completed single-series lookup.",
        )


class NaturalLanguageQueryServiceTest(unittest.TestCase):
    def test_routes_completed_state_comparison(self) -> None:
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
        service = NaturalLanguageQueryService(
            parser=_FakeParser(intent),
            fred_client=_FakeFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            single_series_service=_FakeSingleSeriesService(),
        )

        response = service.ask("How has California GDP compared to Texas since 2019?")

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertEqual(response.answer_text, "Completed comparison.")

    def test_returns_clarification_with_candidates(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_question="Do you mean CPI or PCE inflation?",
            search_text="inflation united states",
        )
        service = NaturalLanguageQueryService(
            parser=_FakeParser(intent),
            fred_client=_FakeFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            single_series_service=_FakeSingleSeriesService(),
        )

        response = service.ask("Show inflation.")

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertIn("CPI or PCE", response.answer_text)
        self.assertEqual(response.candidate_series[0].series_id, "UNRATE")

    def test_selected_series_id_executes_lookup(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_question="Do you mean CPI or PCE inflation?",
            search_text="inflation united states",
        )
        service = NaturalLanguageQueryService(
            parser=_FakeParser(intent),
            fred_client=_FakeFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            single_series_service=_FakeSingleSeriesService(),
        )

        response = service.ask("Show inflation.", selected_series_id="CPIAUCSL")

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertEqual(response.query_response.intent.series_id, "CPIAUCSL")
        self.assertFalse(response.query_response.intent.clarification_needed)

    def test_raises_when_primary_parser_fails(self) -> None:
        service = NaturalLanguageQueryService(
            parser=_FailingParser(),
            fred_client=_FakeFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            single_series_service=_FakeSingleSeriesService(),
        )

        with self.assertRaises(RuntimeError):
            service.ask("How has California GDP compared to Texas since 2019?")


if __name__ == "__main__":
    unittest.main()
