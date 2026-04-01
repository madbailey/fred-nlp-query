from __future__ import annotations

from datetime import date
import unittest

from fred_query.api.follow_up_suggestions import build_follow_up_suggestions
from fred_query.api.models import ApiQueryResponse
from fred_query.schemas.analysis import AnalysisResult, HistoricalSeriesContext, QueryResponse, SeriesAnalysis
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
from fred_query.schemas.resolved_series import ResolvedSeries


def _series(
    *,
    series_id: str,
    title: str,
    indicator: str,
    geography: str,
    units: str = "Percent",
    frequency: str = "M",
) -> ResolvedSeries:
    return ResolvedSeries(
        series_id=series_id,
        title=title,
        geography=geography,
        indicator=indicator,
        units=units,
        frequency=frequency,
        resolution_reason="fixture",
        source_url=f"https://fred.stlouisfed.org/series/{series_id}",
    )


class FollowUpSuggestionsTest(unittest.TestCase):
    def test_single_series_suggestions_cover_comparison_transform_and_peak(self) -> None:
        response = QueryResponse(
            intent=QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                search_text="unemployment rate",
                indicators=["unemployment rate"],
                start_date=date(2020, 1, 1),
                transform=TransformType.LEVEL,
            ),
            analysis=AnalysisResult(
                series_results=[
                    SeriesAnalysis(
                        series=_series(
                            series_id="UNRATE",
                            title="Unemployment Rate",
                            indicator="unemployment_rate",
                            geography="United States",
                        ),
                        latest_value=4.1,
                        latest_observation_date=date(2024, 1, 1),
                        historical_context=HistoricalSeriesContext(
                            start_date=date(1976, 1, 1),
                            end_date=date(2024, 1, 1),
                            observation_count=48,
                            average_value=5.8,
                            percentile_rank=42.0,
                            min_value=3.4,
                            min_date=date(1969, 5, 1),
                            max_value=14.8,
                            max_date=date(2020, 4, 1),
                        ),
                    )
                ],
                coverage_start=date(2020, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                title="Unemployment Rate",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Percent"),
                series=[ChartTrace(name="UNRATE")],
                source_note="Source: FRED",
            ),
            answer_text="Completed single-series lookup.",
        )

        suggestions = build_follow_up_suggestions(response)

        self.assertEqual(
            [item.query for item in suggestions],
            [
                "Compare United States Unemployment Rate to inflation over the same period",
                "Show United States Unemployment Rate as year-over-year change",
                "When did United States Unemployment Rate peak during this period?",
            ],
        )

    def test_relationship_suggestions_cover_subject_swap_and_range_changes(self) -> None:
        response = QueryResponse(
            intent=QueryIntent(
                task_type=TaskType.RELATIONSHIP_ANALYSIS,
                comparison_mode=ComparisonMode.RELATIONSHIP,
                search_texts=["brent crude oil prices", "inflation"],
                start_date=date(2010, 1, 1),
            ),
            analysis=AnalysisResult(
                series_results=[
                    SeriesAnalysis(
                        series=_series(
                            series_id="DCOILBRENTEU",
                            title="Crude Oil Prices: Brent - Europe",
                            indicator="brent_oil",
                            geography="Global",
                        ),
                    ),
                    SeriesAnalysis(
                        series=_series(
                            series_id="CPIAUCSL",
                            title="Consumer Price Index for All Urban Consumers",
                            indicator="inflation",
                            geography="United States",
                        ),
                    ),
                ],
                coverage_start=date(2010, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                title="Relationship Analysis",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Standard deviations"),
                series=[ChartTrace(name="oil"), ChartTrace(name="inflation")],
                source_note="Source: FRED",
            ),
            answer_text="Completed relationship analysis.",
        )

        suggestions = build_follow_up_suggestions(response)

        self.assertEqual(
            [item.query for item in suggestions],
            [
                "Compare Global Crude Oil Prices: Brent - Europe to unemployment instead",
                "Show Global Crude Oil Prices: Brent - Europe and United States Consumer Price Index for All Urban Consumers as year-over-year change",
                "Extend this back to 2000",
            ],
        )

    def test_cross_section_suggestions_cover_ranking_controls(self) -> None:
        response = QueryResponse(
            intent=QueryIntent(
                task_type=TaskType.CROSS_SECTION,
                comparison_mode=ComparisonMode.CROSS_SECTION,
                cross_section_scope=CrossSectionScope.STATES,
                search_text="unemployment rate",
                indicators=["unemployment rate"],
                sort_descending=True,
                rank_limit=10,
                observation_date=date(2024, 1, 1),
            ),
            analysis=AnalysisResult(
                series_results=[
                    SeriesAnalysis(
                        series=_series(
                            series_id=f"S{i}",
                            title=f"State {i} Unemployment Rate",
                            indicator="unemployment_rate",
                            geography=f"State {i}",
                        ),
                        latest_value=float(i),
                        latest_observation_date=date(2024, 1, 1),
                    )
                    for i in range(10)
                ],
                coverage_start=date(2024, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                chart_type="bar",
                title="State Ranking",
                x_axis=AxisSpec(title="State"),
                y_axis=AxisSpec(title="Percent"),
                series=[ChartTrace(name="ranking")],
                source_note="Source: FRED",
            ),
            answer_text="Completed cross-section analysis.",
        )

        suggestions = build_follow_up_suggestions(response)

        self.assertEqual(
            [item.query for item in suggestions],
            [
                "Rank the bottom 10 states by unemployment rate instead",
                "Rank the top 5 states by unemployment rate",
                "Use the latest available observation instead",
            ],
        )

    def test_state_gdp_suggestions_include_normalization_toggle(self) -> None:
        response = QueryResponse(
            intent=QueryIntent(
                task_type=TaskType.STATE_GDP_COMPARISON,
                comparison_mode=ComparisonMode.STATE_VS_STATE,
                geographies=[
                    Geography(name="California", geography_type=GeographyType.STATE),
                    Geography(name="Texas", geography_type=GeographyType.STATE),
                ],
                start_date=date(2019, 1, 1),
                transform=TransformType.NORMALIZED_INDEX,
                normalization=True,
            ),
            analysis=AnalysisResult(
                series_results=[
                    SeriesAnalysis(
                        series=_series(
                            series_id="CARGSP",
                            title="Real GDP: California",
                            indicator="real_gdp",
                            geography="California",
                            units="Billions of Dollars",
                            frequency="A",
                        )
                    ),
                    SeriesAnalysis(
                        series=_series(
                            series_id="TXRGSP",
                            title="Real GDP: Texas",
                            indicator="real_gdp",
                            geography="Texas",
                            units="Billions of Dollars",
                            frequency="A",
                        )
                    ),
                ],
                coverage_start=date(2019, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                title="Real GDP Comparison",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Index"),
                series=[ChartTrace(name="California"), ChartTrace(name="Texas")],
                source_note="Source: FRED",
            ),
            answer_text="Completed comparison.",
        )

        api_response = ApiQueryResponse.from_query_response(response)

        self.assertEqual(
            [item.query for item in api_response.follow_up_suggestions],
            [
                "Show Real GDP: California and Real GDP: Texas in reported GDP levels instead",
                "Extend this back to 2000",
            ],
        )

    def test_single_series_yoy_suggestion_toggles_back_to_levels(self) -> None:
        response = QueryResponse(
            intent=QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                search_text="inflation",
                indicators=["inflation"],
                transform=TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE,
            ),
            analysis=AnalysisResult(
                series_results=[
                    SeriesAnalysis(
                        series=_series(
                            series_id="CPIAUCSL",
                            title="Consumer Price Index for All Urban Consumers",
                            indicator="inflation",
                            geography="United States",
                        ),
                        latest_value=3.1,
                        latest_observation_date=date(2024, 1, 1),
                    )
                ],
                coverage_start=date(2015, 1, 1),
                coverage_end=date(2024, 1, 1),
            ),
            chart=ChartSpec(
                title="Inflation",
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Percent"),
                series=[ChartTrace(name="CPIAUCSL")],
                source_note="Source: FRED",
            ),
            answer_text="Completed single-series lookup.",
        )

        suggestions = build_follow_up_suggestions(response)

        self.assertIn(
            "Show United States Consumer Price Index for All Urban Consumers in reported levels instead",
            [item.query for item in suggestions],
        )


if __name__ == "__main__":
    unittest.main()
