from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import ObservationPoint, SeriesAnalysis
from fred_query.schemas.resolved_series import ResolvedSeries
from fred_query.services.chart_service import ChartService


def _build_series_analysis(
    *,
    series_id: str,
    title: str,
    geography: str,
    indicator: str,
) -> SeriesAnalysis:
    return SeriesAnalysis(
        series=ResolvedSeries(
            series_id=series_id,
            title=title,
            geography=geography,
            indicator=indicator,
            units="Index",
            frequency="M",
            resolution_reason="fixture",
            source_url=f"https://fred.stlouisfed.org/series/{series_id}",
        ),
        transformed_observations=[
            ObservationPoint(date=date(2010, 1, 1), value=100.0),
            ObservationPoint(date=date(2010, 2, 1), value=101.5),
        ],
    )


class ChartServiceTest(unittest.TestCase):
    def test_relationship_chart_uses_human_readable_series_labels(self) -> None:
        service = ChartService()
        brent = _build_series_analysis(
            series_id="DCOILBRENTEU",
            title="Crude Oil Prices: Brent - Europe",
            geography="Unspecified",
            indicator="brent crude oil prices",
        )
        cpi = _build_series_analysis(
            series_id="CPIAUCSL",
            title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
            geography="Unspecified",
            indicator="inflation",
        )

        chart = service.build_relationship_chart(
            series_results=[brent, cpi],
            frequency_label="Monthly",
            chart_basis="Standardized relationship basis",
            chart_units="Standard deviations",
            start_date=date(2010, 1, 1),
            end_date=date(2026, 1, 1),
        )

        self.assertEqual(
            chart.title,
            "Crude Oil Prices: Brent - Europe vs Consumer Price Index for All Urban Consumers",
        )
        self.assertEqual(
            [trace.name for trace in chart.series],
            [
                "Crude Oil Prices: Brent - Europe",
                "Consumer Price Index for All Urban Consumers",
            ],
        )

    def test_single_series_chart_uses_series_title_for_trace_name(self) -> None:
        service = ChartService()
        unemployment = SeriesAnalysis(
            series=ResolvedSeries(
                series_id="UNRATE",
                title="Unemployment Rate",
                geography="United States",
                indicator="unemployment_rate",
                units="Percent",
                frequency="M",
                resolution_reason="fixture",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            ),
            observations=[
                ObservationPoint(date=date(2020, 1, 1), value=3.5),
                ObservationPoint(date=date(2020, 2, 1), value=3.6),
            ],
            latest_value=3.6,
            latest_observation_date=date(2020, 2, 1),
        )

        chart = service.build_single_series_chart(
            series_result=unemployment,
            start_year=2020,
            end_year=2020,
            normalize=False,
            recession_periods=[],
        )

        self.assertEqual(chart.series[0].name, "Unemployment Rate")

    def test_cross_section_chart_assigns_distinct_colors_across_large_rankings(self) -> None:
        service = ChartService()
        series_results = [
            SeriesAnalysis(
                series=ResolvedSeries(
                    series_id=f"S{i:02d}",
                    title=f"Series {i}",
                    geography=f"State {i}",
                    indicator="fixture",
                    units="Percent",
                    frequency="M",
                    resolution_reason="fixture",
                    source_url=f"https://fred.stlouisfed.org/series/S{i:02d}",
                ),
                latest_value=float(i),
                latest_observation_date=date(2024, 1, 1),
            )
            for i in range(12)
        ]

        chart = service.build_cross_section_chart(
            series_results=series_results,
            title="State ranking",
            subtitle="Latest values",
            y_axis_title="Percent",
        )
        plotly_figure = chart.to_plotly_dict()

        self.assertEqual(len(chart.series[0].line.color), 12)
        self.assertEqual(len(set(chart.series[0].line.color)), 12)
        self.assertEqual(
            plotly_figure["data"][0]["marker"]["color"],
            chart.series[0].line.color,
        )


if __name__ == "__main__":
    unittest.main()
