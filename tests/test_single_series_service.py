from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.intent import QueryIntent, TaskType
from fred_query.schemas.resolved_series import SeriesMetadata
from fred_query.services.single_series_service import SingleSeriesLookupService


class _FakeFREDClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, date | None, date | None]] = []

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return SeriesMetadata(
            series_id=series_id,
            title="Unemployment Rate",
            units="Percent",
            frequency="Annual",
            seasonal_adjustment="SA",
            source_url=f"https://fred.stlouisfed.org/series/{series_id}",
        )

    def get_series_observations(
        self,
        series_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        frequency: str | None = None,
        aggregation_method: str | None = None,
        limit: int | None = None,
        sort_order: str | None = None,
    ) -> list[ObservationPoint]:
        self.requests.append((series_id, start_date, end_date))
        if series_id == "USREC":
            return []
        if series_id != "UNRATE":
            raise AssertionError(f"Unexpected series request: {series_id}")
        if start_date == date(2022, 1, 1) and end_date is None:
            return [
                ObservationPoint(date=date(2022, 1, 1), value=4.8),
                ObservationPoint(date=date(2023, 1, 1), value=4.4),
                ObservationPoint(date=date(2024, 1, 1), value=4.1),
            ]
        if start_date == date(1974, 1, 1) and end_date == date(2024, 1, 1):
            return [
                ObservationPoint(date=date(1974, 1, 1), value=8.0),
                ObservationPoint(date=date(1990, 1, 1), value=6.5),
                ObservationPoint(date=date(2000, 1, 1), value=5.5),
                ObservationPoint(date=date(2010, 1, 1), value=9.0),
                ObservationPoint(date=date(2020, 1, 1), value=14.7),
                ObservationPoint(date=date(2024, 1, 1), value=4.1),
            ]
        raise AssertionError(f"Unexpected observation window: {start_date} to {end_date}")


class SingleSeriesLookupServiceTest(unittest.TestCase):
    def test_lookup_adds_historical_context_to_answer(self) -> None:
        client = _FakeFREDClient()
        service = SingleSeriesLookupService(client)
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            series_id="UNRATE",
            start_date=date(2022, 1, 1),
        )

        response = service.lookup(intent)

        self.assertEqual(
            client.requests,
            [
                ("UNRATE", date(2022, 1, 1), None),
                ("UNRATE", date(1974, 1, 1), date(2024, 1, 1)),
                ("USREC", date(2022, 1, 1), date(2024, 1, 1)),
            ],
        )
        self.assertAlmostEqual(
            response.analysis.series_results[0].historical_context.average_value or 0.0,
            7.9667,
            places=4,
        )
        metric_names = {metric.name for metric in response.analysis.derived_metrics}
        self.assertIn("historical_average", metric_names)
        self.assertIn("historical_percentile_rank", metric_names)
        self.assertIn("historical_peak", metric_names)
        self.assertIn("historical_trough", metric_names)
        self.assertIn("below the 50-year average of 7.97%", response.answer_text)
        self.assertIn("17th percentile", response.answer_text)
        self.assertIn("well below the 2020 peak of 14.70%", response.answer_text)


if __name__ == "__main__":
    unittest.main()
