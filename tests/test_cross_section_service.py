from __future__ import annotations

from datetime import date
import json
import unittest
from unittest.mock import patch

import httpx

from fred_query.schemas.intent import ComparisonMode, CrossSectionScope, QueryIntent, TaskType
from fred_query.services.cross_section_service import CrossSectionService
from fred_query.services.fred_client import FREDClient


class CrossSectionServiceTest(unittest.TestCase):
    def _build_state_ranking_client(self) -> tuple[FREDClient, list[dict[str, str]]]:
        requests: list[dict[str, str]] = []
        metadata_payloads = {
            "CAUR": {
                "seriess": [
                    {
                        "id": "CAUR",
                        "title": "Unemployment Rate in California",
                        "units_short": "Percent",
                        "frequency_short": "M",
                        "seasonal_adjustment_short": "SA",
                    }
                ]
            },
            "TXUR": {
                "seriess": [
                    {
                        "id": "TXUR",
                        "title": "Unemployment Rate in Texas",
                        "units_short": "Percent",
                        "frequency_short": "M",
                        "seasonal_adjustment_short": "SA",
                    }
                ]
            },
            "NVUR": {
                "seriess": [
                    {
                        "id": "NVUR",
                        "title": "Unemployment Rate in Nevada",
                        "units_short": "Percent",
                        "frequency_short": "M",
                        "seasonal_adjustment_short": "SA",
                    }
                ]
            },
        }
        observation_payloads = {
            "CAUR": {"observations": [{"date": "2024-01-01", "value": "5.0"}]},
            "TXUR": {"observations": [{"date": "2024-01-01", "value": "4.0"}]},
            "NVUR": {"observations": [{"date": "2024-01-01", "value": "6.5"}]},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(dict(request.url.params))
            if request.url.path.endswith("/series"):
                series_id = request.url.params["series_id"]
                return httpx.Response(status_code=200, text=json.dumps(metadata_payloads[series_id]))
            if request.url.path.endswith("/series/observations"):
                series_id = request.url.params["series_id"]
                return httpx.Response(status_code=200, text=json.dumps(observation_payloads[series_id]))
            return httpx.Response(status_code=404, json={"error_message": "not found"})

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://example.test/fred", transport=transport)
        client = FREDClient(api_key="test-key", base_url="https://example.test/fred", http_client=http_client)
        return client, requests

    def _build_single_series_client(self) -> FREDClient:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/series/search"):
                payload = {
                    "seriess": [
                        {
                            "id": "CPIAUCSL",
                            "title": "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                            "units_short": "Index 1982-1984=100",
                            "frequency_short": "M",
                            "seasonal_adjustment_short": "SA",
                            "popularity": 99,
                        }
                    ]
                }
                return httpx.Response(status_code=200, text=json.dumps(payload))
            if request.url.path.endswith("/series"):
                payload = {
                    "seriess": [
                        {
                            "id": "CPIAUCSL",
                            "title": "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                            "units_short": "Index 1982-1984=100",
                            "frequency_short": "M",
                            "seasonal_adjustment_short": "SA",
                        }
                    ]
                }
                return httpx.Response(status_code=200, text=json.dumps(payload))
            if request.url.path.endswith("/series/observations"):
                payload = {"observations": [{"date": "2023-01-01", "value": "300.54"}]}
                return httpx.Response(status_code=200, text=json.dumps(payload))
            return httpx.Response(status_code=404, json={"error_message": "not found"})

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://example.test/fred", transport=transport)
        return FREDClient(api_key="test-key", base_url="https://example.test/fred", http_client=http_client)

    def test_ranks_state_cross_section_and_builds_bar_chart(self) -> None:
        client, requests = self._build_state_ranking_client()
        service = CrossSectionService(client)
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            indicators=["unemployment rate"],
            search_text="unemployment rate",
            comparison_mode=ComparisonMode.CROSS_SECTION,
            cross_section_scope=CrossSectionScope.STATES,
            rank_limit=2,
        )

        with patch.dict(
            "fred_query.services.cross_section_service.STATE_CODE_TO_NAME",
            {"CA": "California", "TX": "Texas", "NV": "Nevada"},
            clear=True,
        ):
            response = service.analyze(intent)

        self.assertEqual(response.intent.cross_section_scope, CrossSectionScope.STATES)
        self.assertEqual(response.chart.chart_type, "bar")
        self.assertEqual(
            [result.series.geography for result in response.analysis.series_results],
            ["Nevada", "California"],
        )
        self.assertEqual(response.chart.series[0].x, ["Nevada", "California"])
        self.assertEqual(response.chart.series[0].y, [6.5, 5.0])
        self.assertIn("Nevada ranks highest", response.answer_text)
        observation_requests = [item for item in requests if item.get("series_id") in {"CAUR", "TXUR", "NVUR"} and item.get("sort_order") == "desc"]
        self.assertEqual(len(observation_requests), 3)
        self.assertTrue(all(item.get("limit") == "1" for item in observation_requests))
        self.assertEqual(response.chart.to_plotly_dict()["data"][0]["type"], "bar")

    def test_single_series_point_in_time_snapshot_returns_single_bar(self) -> None:
        client = self._build_single_series_client()
        service = CrossSectionService(client)
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            indicators=["inflation"],
            search_text="inflation",
            cross_section_scope=CrossSectionScope.SINGLE_SERIES,
            observation_date=date(2023, 1, 1),
        )

        response = service.analyze(intent)

        self.assertEqual(response.intent.comparison_mode, ComparisonMode.CROSS_SECTION)
        self.assertEqual(response.chart.chart_type, "bar")
        self.assertEqual(response.chart.series[0].x, ["CPIAUCSL"])
        self.assertEqual(response.chart.series[0].y, [300.54])
        self.assertEqual(response.analysis.series_results[0].latest_observation_date, date(2023, 1, 1))
        self.assertIn("2023-01-01", response.answer_text)


if __name__ == "__main__":
    unittest.main()
