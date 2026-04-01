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
    def _build_state_ranking_client(
        self,
        state_values: dict[str, tuple[str, float]] | None = None,
    ) -> tuple[FREDClient, list[dict[str, str]]]:
        requests: list[dict[str, str]] = []
        state_values = state_values or {
            "CA": ("California", 5.0),
            "TX": ("Texas", 4.0),
            "NV": ("Nevada", 6.5),
        }
        metadata_payloads = {}
        observation_payloads = {}
        for state_code, (state_name, value) in state_values.items():
            series_id = f"{state_code}UR"
            metadata_payloads[series_id] = {
                "seriess": [
                    {
                        "id": series_id,
                        "title": f"Unemployment Rate in {state_name}",
                        "units_short": "Percent",
                        "frequency_short": "M",
                        "seasonal_adjustment_short": "SA",
                    }
                ]
            }
            observation_payloads[series_id] = {"observations": [{"date": "2024-01-01", "value": str(value)}]}

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
        self.assertEqual(response.chart.series[0].x_categories, ["Nevada", "California"])
        self.assertEqual(response.chart.series[0].y, [6.5, 5.0])
        self.assertIsNotNone(response.analysis.cross_section_summary)
        self.assertEqual(response.analysis.cross_section_summary.leader_label, "Nevada")
        self.assertIn("Nevada ranks highest", response.answer_text)
        observation_requests = [item for item in requests if item.get("series_id") in {"CAUR", "TXUR", "NVUR"} and item.get("sort_order") == "desc"]
        self.assertEqual(len(observation_requests), 3)
        self.assertTrue(all(item.get("limit") == "1" for item in observation_requests))
        self.assertEqual(response.chart.to_plotly_dict()["data"][0]["type"], "bar")

    def test_highest_state_query_defaults_to_top_ten_for_context(self) -> None:
        state_values = {
            "AL": ("Alabama", 3.1),
            "AK": ("Alaska", 6.2),
            "AZ": ("Arizona", 4.1),
            "AR": ("Arkansas", 3.9),
            "CA": ("California", 5.0),
            "CO": ("Colorado", 3.4),
            "CT": ("Connecticut", 4.0),
            "DE": ("Delaware", 4.4),
            "FL": ("Florida", 3.2),
            "GA": ("Georgia", 3.3),
            "HI": ("Hawaii", 2.8),
            "NV": ("Nevada", 6.5),
        }
        client, _ = self._build_state_ranking_client(state_values)
        service = CrossSectionService(client)
        intent = QueryIntent(
            task_type=TaskType.CROSS_SECTION,
            original_query="Which state has the highest unemployment rate?",
            indicators=["unemployment rate"],
            search_text="unemployment rate",
            comparison_mode=ComparisonMode.CROSS_SECTION,
            cross_section_scope=CrossSectionScope.STATES,
            rank_limit=1,
        )

        with patch.dict(
            "fred_query.services.cross_section_service.STATE_CODE_TO_NAME",
            {state_code: state_name for state_code, (state_name, _) in state_values.items()},
            clear=True,
        ):
            response = service.analyze(intent)

        self.assertEqual(len(response.analysis.series_results), 10)
        self.assertEqual(response.intent.rank_limit, 10)
        self.assertEqual(response.analysis.series_results[0].series.geography, "Nevada")
        self.assertEqual(response.analysis.cross_section_summary.display_selection_basis, "comparison_context")
        self.assertEqual(response.chart.series[0].x_categories[0], "Nevada")
        self.assertIn("comparison context around the leader", response.answer_text)
        self.assertIn("Showing 10 of 12 series for comparison context.", response.chart.subtitle or "")

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
        self.assertEqual(response.chart.series[0].x_categories, ["CPIAUCSL"])
        self.assertEqual(response.chart.series[0].y, [300.54])
        self.assertEqual(response.analysis.series_results[0].latest_observation_date, date(2023, 1, 1))
        self.assertEqual(response.analysis.cross_section_summary.resolved_series_count, 1)
        self.assertIn("2023-01-01", response.answer_text)


if __name__ == "__main__":
    unittest.main()
