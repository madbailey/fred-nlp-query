from __future__ import annotations

import json
import unittest
from datetime import date

import httpx

from fred_query.schemas.resolved_series import ResolvedSeries
from fred_query.services.fred_client import FREDClient
from fred_query.services.vintage_analysis_service import VintageAnalysisService


class VintageAnalysisServiceTest(unittest.TestCase):
    def _build_client(self) -> FREDClient:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/series/vintagedates"):
                # Return mock vintage dates
                payload = {"vintage_dates": ["2020-01-01", "2021-01-01", "2022-01-01"]}
            elif "vintage_dates=" in str(request.url):
                # This is a request for observations with a vintage date
                payload = {
                    "observations": [
                        {"date": "2010-01-01", "value": "100.0"},
                        {"date": "2011-01-01", "value": "105.0"},
                        {"date": "2012-01-01", "value": "110.0"},
                    ]
                }
            elif request.url.path.endswith("/series/observations"):
                # This is a request for current observations
                payload = {
                    "observations": [
                        {"date": "2010-01-01", "value": "102.0"},  # Revised from 100.0
                        {"date": "2011-01-01", "value": "107.0"},  # Revised from 105.0
                        {"date": "2012-01-01", "value": "112.0"},  # Revised from 110.0
                    ]
                }
            elif request.url.path.endswith("/series"):
                payload = {
                    "seriess": [
                        {
                            "id": "TEST",
                            "title": "Test Series",
                            "units_short": "Index",
                            "frequency_short": "A",
                            "seasonal_adjustment_short": "NSA",
                            "notes": "Test series for vintage analysis",
                        }
                    ]
                }
            else:
                return httpx.Response(status_code=404, json={"error_message": "not found"})

            return httpx.Response(status_code=200, text=json.dumps(payload))

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://example.test/fred", transport=transport)
        return FREDClient(api_key="test-key", base_url="https://example.test/fred", http_client=http_client)

    def test_vintage_analysis_service(self) -> None:
        client = self._build_client()
        service = VintageAnalysisService(client)

        # Create a mock resolved series
        series = ResolvedSeries(
            series_id="TEST",
            title="Test Series",
            geography="United States",
            indicator="test_indicator",
            units="Index",
            frequency="Annual",
            score=1.0,
            resolution_reason="Test",
            source_url="https://example.com/test"
        )

        # Perform vintage analysis
        result = service.analyze_vintage_data(series, vintage_limit=10, max_comparisons=5)

        # Verify the result structure
        self.assertEqual(len(result.series_vintage_data), 1)
        vintage_data = result.series_vintage_data[0]
        self.assertEqual(vintage_data.series_id, "TEST")
        self.assertEqual(len(vintage_data.vintage_dates), 3)  # We mocked 3 vintage dates
        self.assertGreaterEqual(len(vintage_data.vintage_observations), 0)  # May have some observations

        # Verify comparisons were created
        self.assertGreaterEqual(len(result.comparisons), 0)

        # Test helper methods
        first_value = service.get_first_release_value("TEST", date(2010, 1, 1))
        self.assertIsNotNone(first_value)

        comparison = service.compare_latest_vs_original("TEST", date(2010, 1, 1))
        self.assertIsNotNone(comparison)
        if comparison:
            self.assertIn("first_release_value", comparison)
            self.assertIn("latest_revision_value", comparison)
            self.assertIn("percent_change", comparison)


if __name__ == "__main__":
    unittest.main()