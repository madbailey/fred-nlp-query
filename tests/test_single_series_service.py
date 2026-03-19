from __future__ import annotations

from datetime import date, timedelta
import unittest

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.intent import QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import SeriesMetadata
from fred_query.services.single_series_service import SingleSeriesLookupService


class _HistoricalUnemploymentFREDClient:
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


class _DailyVolatilityFREDClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, date | None, date | None]] = []
        self.base_date = date(1970, 1, 1)

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return SeriesMetadata(
            series_id=series_id,
            title="S&P 500",
            units="Index",
            frequency="Daily",
            seasonal_adjustment="NSA",
            source_url=f"https://fred.stlouisfed.org/series/{series_id}",
        )

    def _value_for_date(self, current_date: date) -> float:
        offset = (current_date - self.base_date).days
        cycle = ((offset % 14) - 7) * 6.0
        return 1000.0 + (offset * 0.35) + cycle

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
        if series_id != "SP500":
            raise AssertionError(f"Unexpected series request: {series_id}")

        current_date = start_date or date(2024, 1, 1)
        final_date = end_date or date(2024, 4, 30)
        observations: list[ObservationPoint] = []
        while current_date <= final_date:
            observations.append(
                ObservationPoint(
                    date=current_date,
                    value=self._value_for_date(current_date),
                )
            )
            current_date += timedelta(days=1)
        return observations


class SingleSeriesLookupServiceTest(unittest.TestCase):
    def test_lookup_adds_historical_context_to_answer(self) -> None:
        client = _HistoricalUnemploymentFREDClient()
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

    def test_lookup_supports_rolling_volatility_with_default_window(self) -> None:
        client = _DailyVolatilityFREDClient()
        service = SingleSeriesLookupService(client)
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            series_id="SP500",
            start_date=date(2024, 2, 1),
            transform=TransformType.ROLLING_VOLATILITY,
        )

        response = service.lookup(intent)

        self.assertEqual(client.requests[0], ("SP500", date(2024, 1, 2), None))
        self.assertIn(
            "Used a default 30-observation rolling window because the query did not specify one.",
            response.analysis.warnings,
        )
        result = response.analysis.series_results[0]
        self.assertEqual(result.analysis_basis, "30-observation rolling annualized volatility")
        self.assertEqual(result.analysis_units, "Percent")
        self.assertEqual(result.transformed_observations[0].date, date(2024, 2, 1))
        self.assertEqual(response.chart.y_axis.title, "Percent")
        self.assertIn("rolling annualized volatility", response.answer_text)
        metric_names = {metric.name for metric in response.analysis.derived_metrics}
        self.assertIn("applied_transform_window", metric_names)


if __name__ == "__main__":
    unittest.main()
