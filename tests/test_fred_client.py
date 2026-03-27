from __future__ import annotations

from datetime import date
import json
import unittest

import httpx

from fred_query.services.fred_client import FREDClient


class FREDClientTest(unittest.TestCase):
    def _build_client(self) -> FREDClient:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/series/search"):
                payload = {
                    "seriess": [
                        {
                            "id": "CARGSP",
                            "title": "Real GDP: California",
                            "units_short": "Bil. of Chn. 2017 Dollars",
                            "frequency_short": "A",
                            "seasonal_adjustment_short": "NSA",
                            "popularity": 88,
                        }
                    ]
                }
            elif request.url.path.endswith("/series"):
                payload = {
                    "seriess": [
                        {
                            "id": "CARGSP",
                            "title": "Real GDP: California",
                            "units_short": "Bil. of Chn. 2017 Dollars",
                            "frequency_short": "A",
                            "seasonal_adjustment_short": "NSA",
                            "notes": "Sample notes",
                        }
                    ]
                }
            elif request.url.path.endswith("/series/observations"):
                # Check if the request includes vintage dates parameter
                if "vintage_dates" in request.url.params:
                    # Handle the case where vintage dates are specified
                    payload = {
                        "observations": [
                            {"date": "2010-01-01", "value": "100.0"},
                            {"date": "2011-01-01", "value": "110.5"},
                            {"date": "2012-01-01", "value": "125.0"},
                        ]
                    }
                else:
                    # Regular observations request (without vintage dates)
                    payload = {
                        "observations": [
                            {"date": "2010-01-01", "value": "100.0"},
                            {"date": "2011-01-01", "value": "."},
                            {"date": "2012-01-01", "value": "125.0"},
                        ]
                    }
            elif request.url.path.endswith("/series/vintagedates"):
                payload = {"vintage_dates": ["2020-01-01", "2021-01-01"]}
            else:
                return httpx.Response(status_code=404, json={"error_message": "not found"})

            return httpx.Response(status_code=200, text=json.dumps(payload))

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://example.test/fred", transport=transport)
        return FREDClient(api_key="test-key", base_url="https://example.test/fred", http_client=http_client)

    def test_series_endpoints_are_parsed(self) -> None:
        client = self._build_client()

        matches = client.search_series("california gdp", limit=1)
        metadata = client.get_series_metadata("CARGSP")
        observations = client.get_series_observations("CARGSP", start_date=date(2010, 1, 1))
        vintage_dates = client.get_series_vintage_dates("CARGSP")

        # Test the new vintage observations functionality
        vintage_obs = client.get_series_observations_for_vintage_date(
            "CARGSP",
            date(2020, 1, 1),
            start_date=date(2010, 1, 1)
        )

        self.assertEqual(matches[0].series_id, "CARGSP")
        self.assertEqual(metadata.title, "Real GDP: California")
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[-1].value, 125.0)
        self.assertEqual(vintage_dates[-1], date(2021, 1, 1))
        self.assertEqual(len(vintage_obs), 3)  # Should have 3 observations from the mock
        self.assertEqual(vintage_obs[0].value, 100.0)


if __name__ == "__main__":
    unittest.main()
