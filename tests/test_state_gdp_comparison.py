from __future__ import annotations

from datetime import date
import json
import unittest

import httpx

from fred_query.services.comparison_service import StateGDPComparisonService
from fred_query.services.fred_client import FREDClient


class StateGDPComparisonServiceTest(unittest.TestCase):
    def _build_client(self) -> FREDClient:
        metadata_payloads = {
            "CARGSP": {
                "seriess": [
                    {
                        "id": "CARGSP",
                        "title": "Real GDP: California",
                        "units_short": "Millions of Chained 2017 Dollars",
                        "frequency_short": "A",
                        "seasonal_adjustment_short": "NSA",
                    }
                ]
            },
            "TXRGSP": {
                "seriess": [
                    {
                        "id": "TXRGSP",
                        "title": "Real GDP: Texas",
                        "units_short": "Millions of Chained 2017 Dollars",
                        "frequency_short": "A",
                        "seasonal_adjustment_short": "NSA",
                    }
                ]
            },
        }
        observation_payloads = {
            "CARGSP": {
                "observations": [
                    {"date": "2010-01-01", "value": "1800000"},
                    {"date": "2011-01-01", "value": "1890000"},
                    {"date": "2012-01-01", "value": "1980000"},
                ]
            },
            "TXRGSP": {
                "observations": [
                    {"date": "2010-01-01", "value": "1300000"},
                    {"date": "2011-01-01", "value": "1400000"},
                    {"date": "2012-01-01", "value": "1495000"},
                ]
            },
            "USREC": {
                "observations": [
                    {"date": "2010-01-01", "value": "0"},
                    {"date": "2010-02-01", "value": "0"},
                    {"date": "2010-03-01", "value": "0"},
                ]
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/series"):
                series_id = request.url.params["series_id"]
                return httpx.Response(status_code=200, text=json.dumps(metadata_payloads[series_id]))

            if request.url.path.endswith("/series/observations"):
                series_id = request.url.params["series_id"]
                return httpx.Response(status_code=200, text=json.dumps(observation_payloads[series_id]))

            return httpx.Response(status_code=404, json={"error_message": "not found"})

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://example.test/fred", transport=transport)
        return FREDClient(api_key="test-key", base_url="https://example.test/fred", http_client=http_client)

    def test_compare_california_and_texas(self) -> None:
        client = self._build_client()
        service = StateGDPComparisonService(client)

        response = service.compare(
            state1="California",
            state2="Texas",
            start_date=date(2010, 1, 1),
            end_date=date(2012, 12, 31),
            normalize=True,
        )

        self.assertEqual(response.intent.task_type.value, "state_gdp_comparison")
        self.assertEqual([series.series.series_id for series in response.analysis.series_results], ["CARGSP", "TXRGSP"])
        self.assertEqual(response.chart.y_axis.title, "Index (Base = 100)")
        self.assertIn("California", response.answer_text)
        self.assertEqual(response.analysis.coverage_start, date(2010, 1, 1))
        self.assertEqual(response.analysis.coverage_end, date(2012, 1, 1))


if __name__ == "__main__":
    unittest.main()
