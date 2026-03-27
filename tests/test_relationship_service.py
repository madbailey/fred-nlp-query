from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.intent import ComparisonMode, QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import SeriesMetadata, SeriesSearchMatch
from fred_query.services.relationship_service import RelationshipAnalysisService


class _FakeFREDClient:
    def __init__(self) -> None:
        self.metadata = {
            "DCOILBRENTEU": SeriesMetadata(
                series_id="DCOILBRENTEU",
                title="Crude Oil Prices: Brent - Europe",
                units="U.S. Dollars per Barrel",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/DCOILBRENTEU",
            ),
            "CPIAUCSL": SeriesMetadata(
                series_id="CPIAUCSL",
                title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                units="Index 1982-1984=100",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
            ),
        }
        self.requests: list[tuple[str, str | None, str | None]] = []

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        if "brent" in search_text.lower():
            return [
                SeriesSearchMatch(
                    series_id="DCOILBRENTEU",
                    title=self.metadata["DCOILBRENTEU"].title,
                    units=self.metadata["DCOILBRENTEU"].units,
                    frequency=self.metadata["DCOILBRENTEU"].frequency,
                    source_url=self.metadata["DCOILBRENTEU"].source_url,
                )
            ]
        return [
            SeriesSearchMatch(
                series_id="CPIAUCSL",
                title=self.metadata["CPIAUCSL"].title,
                units=self.metadata["CPIAUCSL"].units,
                frequency=self.metadata["CPIAUCSL"].frequency,
                source_url=self.metadata["CPIAUCSL"].source_url,
            )
        ]

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]

    def get_series_observations(
        self,
        series_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        frequency: str | None = None,
        aggregation_method: str | None = None,
    ) -> list[ObservationPoint]:
        self.requests.append((series_id, frequency, aggregation_method))
        base_values = [100.0 + float(index * index) for index in range(36)]
        if series_id == "CPIAUCSL":
            values = [value * 2.0 for value in base_values]
        else:
            values = base_values

        observations: list[ObservationPoint] = []
        year = 2018
        month = 1
        for value in values:
            observations.append(ObservationPoint(date=date(year, month, 1), value=value))
            month += 1
            if month > 12:
                month = 1
                year += 1
        return observations


class RelationshipAnalysisServiceTest(unittest.TestCase):
    def test_analyze_returns_deterministic_relationship_response(self) -> None:
        client = _FakeFREDClient()
        service = RelationshipAnalysisService(client)
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            comparison_mode=ComparisonMode.RELATIONSHIP,
            indicators=["brent crude oil prices", "inflation"],
            search_texts=["brent crude oil price", "inflation united states"],
            start_date=date(2018, 1, 1),
        )

        response = service.analyze(intent)

        self.assertEqual(len(response.analysis.series_results), 2)
        self.assertEqual(response.analysis.series_results[0].series.series_id, "DCOILBRENTEU")
        self.assertEqual(response.analysis.series_results[1].analysis_basis, "Year-over-year percent change")
        metric_names = {metric.name for metric in response.analysis.derived_metrics}
        self.assertIn("same_period_correlation", metric_names)
        self.assertIn("strongest_lag_periods", metric_names)
        self.assertIn("association estimate", response.answer_text.lower())
        self.assertIn("DCOILBRENTEU", response.answer_text)
        self.assertEqual(client.requests[0], ("DCOILBRENTEU", "m", "avg"))

    def test_analyze_honors_explicit_transform_for_pairwise_requests(self) -> None:
        client = _FakeFREDClient()
        service = RelationshipAnalysisService(client)
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            comparison_mode=ComparisonMode.RELATIONSHIP,
            indicators=["brent crude oil prices", "inflation"],
            search_texts=["brent crude oil price", "inflation united states"],
            start_date=date(2020, 1, 1),
            transform=TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE,
        )

        response = service.analyze(intent)

        self.assertEqual(response.analysis.series_results[0].analysis_basis, "Year-over-year percent change")
        self.assertEqual(response.analysis.series_results[0].analysis_units, "Percent")
        self.assertEqual(response.analysis.series_results[1].analysis_basis, "Year-over-year percent change")
        self.assertEqual(response.analysis.derived_metrics[0].value, "Year-over-year percent change")

    def test_analyze_honors_normalization_for_pairwise_requests(self) -> None:
        client = _FakeFREDClient()
        service = RelationshipAnalysisService(client)
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            comparison_mode=ComparisonMode.RELATIONSHIP,
            indicators=["brent crude oil prices", "inflation"],
            search_texts=["brent crude oil price", "inflation united states"],
            start_date=date(2020, 1, 1),
            transform=TransformType.NORMALIZED_INDEX,
            normalization=True,
        )

        response = service.analyze(intent)

        self.assertEqual(response.analysis.series_results[0].analysis_basis, "Normalized index")
        self.assertEqual(response.analysis.series_results[0].analysis_units, "Index (Base = 100)")
        self.assertEqual(response.analysis.series_results[0].transformed_observations[0].value, 100.0)
        self.assertEqual(response.analysis.derived_metrics[0].value, "Normalized index")


if __name__ == "__main__":
    unittest.main()
