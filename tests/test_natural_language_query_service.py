from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import AnalysisResult, QueryResponse, RoutedQueryStatus, SeriesAnalysis
from fred_query.schemas.chart import AxisSpec, ChartSpec, ChartTrace
from fred_query.schemas.intent import (
    ComparisonMode,
    CrossSectionScope,
    Geography,
    GeographyType,
    QueryIntent,
    TaskType,
    TransformType,
)
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
        lowered = search_text.lower()
        if "cpi" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="CPIAUCSL",
                    title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                    units="Index 1982-1984=100",
                    frequency="M",
                    popularity=95,
                    source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
                )
            ]
        if "pce" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="PCEPI",
                    title="Personal Consumption Expenditures: Chain-type Price Index",
                    units="Index 2017=100",
                    frequency="M",
                    popularity=88,
                    source_url="https://fred.stlouisfed.org/series/PCEPI",
                )
            ]
        return [
            SeriesSearchMatch(
                series_id="UNRATE",
                title="Unemployment Rate",
                units="Percent",
                frequency="M",
                popularity=91,
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            )
        ]


class _InflationClarificationFREDClient:
    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        lowered = search_text.lower()
        if "cpi" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="CPIAUCSL",
                    title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                    units="Index 1982-1984=100",
                    frequency="M",
                    popularity=95,
                    source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
                )
            ]
        if "pce" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="PCEPI",
                    title="Personal Consumption Expenditures: Chain-type Price Index",
                    units="Index 2017=100",
                    frequency="M",
                    popularity=88,
                    source_url="https://fred.stlouisfed.org/series/PCEPI",
                )
            ]
        return [
            SeriesSearchMatch(
                series_id="DFII10",
                title=(
                    "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, "
                    "Quoted on an Investment Basis, Inflation-Indexed"
                ),
                units="Percent",
                frequency="D",
                popularity=42,
                source_url="https://fred.stlouisfed.org/series/DFII10",
            ),
            SeriesSearchMatch(
                series_id="FII10",
                title=(
                    "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, "
                    "Quoted on an Investment Basis, Inflation-Indexed"
                ),
                units="Percent",
                frequency="M",
                popularity=41,
                source_url="https://fred.stlouisfed.org/series/FII10",
            ),
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


class _FakeCrossSectionService:
    def analyze(self, intent: QueryIntent) -> QueryResponse:
        series = ResolvedSeries(
            series_id="CAUR",
            title="Unemployment Rate in California",
            geography="California",
            indicator="unemployment_rate",
            units="Percent",
            frequency="M",
            resolution_reason="fixture",
            source_url="https://fred.stlouisfed.org/series/CAUR",
        )
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(
                series_results=[
                    SeriesAnalysis(
                        series=series,
                        latest_value=5.0,
                        latest_observation_date=date(2024, 1, 1),
                    )
                ],
                coverage_start=date(2024, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                chart_type="bar",
                title="State Ranking: Unemployment Rate",
                x_axis=AxisSpec(title="Series"),
                y_axis=AxisSpec(title="Percent"),
                series=[ChartTrace(name="ranking", x=["California"], y=[5.0])],
                source_note="Source: FRED, Federal Reserve Bank of St. Louis",
            ),
            answer_text="Completed cross-section analysis.",
        )


class _FakeRelationshipService:
    def analyze(self, intent: QueryIntent) -> QueryResponse:
        first = ResolvedSeries(
            series_id="DCOILBRENTEU",
            title="Crude Oil Prices: Brent - Europe",
            geography="Global",
            indicator="brent_oil",
            units="Percent",
            frequency="M",
            resolution_reason="fixture",
            source_url="https://fred.stlouisfed.org/series/DCOILBRENTEU",
        )
        second = ResolvedSeries(
            series_id="CPIAUCSL",
            title="Consumer Price Index for All Urban Consumers",
            geography="United States",
            indicator="inflation",
            units="Percent",
            frequency="M",
            resolution_reason="fixture",
            source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
        )
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(
                series_results=[
                    SeriesAnalysis(series=first, latest_value=1.0, latest_observation_date=date(2024, 1, 1)),
                    SeriesAnalysis(series=second, latest_value=1.0, latest_observation_date=date(2024, 1, 1)),
                ],
                coverage_start=date(2020, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                title="Relationship Analysis: DCOILBRENTEU vs CPIAUCSL",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Percent"),
                series=[ChartTrace(name="DCOILBRENTEU"), ChartTrace(name="CPIAUCSL")],
                source_note="Source: FRED, Federal Reserve Bank of St. Louis",
            ),
            answer_text="Completed relationship analysis.",
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
            cross_section_service=_FakeCrossSectionService(),
            single_series_service=_FakeSingleSeriesService(),
            relationship_service=_FakeRelationshipService(),
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
            cross_section_service=_FakeCrossSectionService(),
            single_series_service=_FakeSingleSeriesService(),
            relationship_service=_FakeRelationshipService(),
        )

        response = service.ask("Show inflation.")

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertIn("CPI or PCE", response.answer_text)
        self.assertEqual(response.candidate_series[0].series_id, "CPIAUCSL")

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
            cross_section_service=_FakeCrossSectionService(),
            single_series_service=_FakeSingleSeriesService(),
            relationship_service=_FakeRelationshipService(),
        )

        response = service.ask("Show inflation.", selected_series_id="CPIAUCSL")

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertEqual(response.query_response.intent.series_id, "CPIAUCSL")
        self.assertFalse(response.query_response.intent.clarification_needed)

    def test_routes_completed_relationship_analysis(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            indicators=["brent crude oil prices", "inflation"],
            search_texts=["brent crude oil price", "inflation united states"],
            comparison_mode=ComparisonMode.RELATIONSHIP,
            start_date=date(2010, 1, 1),
        )
        service = NaturalLanguageQueryService(
            parser=_FakeParser(intent),
            fred_client=_FakeFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            cross_section_service=_FakeCrossSectionService(),
            single_series_service=_FakeSingleSeriesService(),
            relationship_service=_FakeRelationshipService(),
        )

        response = service.ask("What is the relationship between brent crude oil prices and inflation?")

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertEqual(response.answer_text, "Completed relationship analysis.")

    def test_clarification_candidates_prefer_question_examples_over_irrelevant_raw_search_hits(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            clarification_needed=True,
            clarification_target_index=1,
            clarification_question=(
                "Which inflation measure would you like to use for the relationship analysis: "
                "CPI inflation, PCE inflation, or another inflation series?"
            ),
            search_texts=["brent crude oil price", "inflation united states"],
        )
        service = NaturalLanguageQueryService(
            parser=_FakeParser(intent),
            fred_client=_InflationClarificationFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            cross_section_service=_FakeCrossSectionService(),
            single_series_service=_FakeSingleSeriesService(),
            relationship_service=_FakeRelationshipService(),
        )

        response = service.ask("What is the relationship between Brent crude oil prices and inflation since 2010?")

        self.assertEqual(response.status, RoutedQueryStatus.NEEDS_CLARIFICATION)
        self.assertEqual(
            [candidate.series_id for candidate in response.candidate_series],
            ["CPIAUCSL", "PCEPI"],
        )

    def test_raises_when_primary_parser_fails(self) -> None:
        service = NaturalLanguageQueryService(
            parser=_FailingParser(),
            fred_client=_FakeFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            cross_section_service=_FakeCrossSectionService(),
            single_series_service=_FakeSingleSeriesService(),
            relationship_service=_FakeRelationshipService(),
        )

        with self.assertRaises(RuntimeError):
            service.ask("How has California GDP compared to Texas since 2019?")

    def test_routes_completed_cross_section_analysis(self) -> None:
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            indicators=["unemployment rate"],
            search_text="unemployment rate",
            comparison_mode=ComparisonMode.CROSS_SECTION,
            cross_section_scope=CrossSectionScope.STATES,
            rank_limit=10,
        )
        service = NaturalLanguageQueryService(
            parser=_FakeParser(intent),
            fred_client=_FakeFREDClient(),
            state_gdp_service=_FakeStateGDPService(),
            cross_section_service=_FakeCrossSectionService(),
            single_series_service=_FakeSingleSeriesService(),
            relationship_service=_FakeRelationshipService(),
        )

        response = service.ask("Rank the top 10 states by unemployment rate.")

        self.assertEqual(response.status, RoutedQueryStatus.COMPLETED)
        self.assertEqual(response.answer_text, "Completed cross-section analysis.")
        self.assertEqual(response.query_response.chart.chart_type, "bar")


if __name__ == "__main__":
    unittest.main()
