#!/usr/bin/env python3
"""
Demo script showcasing the FRED vintage/revision analysis functionality.
This demonstrates how users can ask "what was the first-release value?"
or compare latest data with the original release.
"""

from datetime import date
import os

from fred_query.services.fred_client import FREDClient
from fred_query.services.vintage_analysis_service import VintageAnalysisService
from fred_query.schemas.resolved_series import ResolvedSeries


def demo_vintage_analysis():
    """Demonstrate vintage analysis functionality"""

    # Get API key from environment or use placeholder for demo
    api_key = os.getenv("FRED_API_KEY", "YOUR_FRED_API_KEY_HERE")

    if api_key == "YOUR_FRED_API_KEY_HERE":
        print("⚠️  WARNING: No FRED API key found. Using mock client for demonstration.")
        print("To use real data, set the FRED_API_KEY environment variable.\n")

        # Create a mock client for demonstration
        import json
        import httpx
        from unittest.mock import Mock

        def mock_handler(request: httpx.Request):
            if request.url.path.endswith("/series/vintagedates"):
                payload = {"vintage_dates": ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"]}
            elif "vintage_dates=" in str(request.url):
                payload = {
                    "observations": [
                        {"date": "2010-01-01", "value": "100.0"},
                        {"date": "2011-01-01", "value": "105.0"},
                        {"date": "2012-01-01", "value": "110.0"},
                    ]
                }
            elif request.url.path.endswith("/series/observations"):
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
                            "title": "Test Economic Indicator",
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

        transport = httpx.MockTransport(mock_handler)
        http_client = httpx.Client(base_url="https://api.stlouisfed.org/fred", transport=transport)
        client = FREDClient(api_key="demo-key", http_client=http_client)
    else:
        # Create real client
        client = FREDClient(api_key=api_key)

    # Create vintage analysis service
    vintage_service = VintageAnalysisService(client)

    print("🔍 FRED Vintage/Revision Analysis Demo")
    print("=" * 50)

    # Example: GDP series that commonly has revisions
    series_id = "GDPC1"  # Real US GDP quarterly series

    if api_key == "YOUR_FRED_API_KEY_HERE":
        # Use mock series for demo
        series_id = "TEST"

    print(f"Analyzing series: {series_id}")
    print()

    try:
        # Get series metadata
        metadata = client.get_series_metadata(series_id)
        print(f"📊 Series: {metadata.title}")
        print(f"   Units: {metadata.units}")
        print(f"   Frequency: {metadata.frequency}")
        print()

        # Get vintage dates for the series
        print("📅 Retrieving vintage dates...")
        vintage_dates = client.get_series_vintage_dates(series_id, limit=10)
        print(f"   Found {len(vintage_dates)} vintage dates")
        if vintage_dates:
            print(f"   Latest vintage: {vintage_dates[-1]}")
            print(f"   Earliest vintage: {vintage_dates[0]}")
        print()

        # Create a resolved series object for the demo
        resolved_series = ResolvedSeries(
            series_id=series_id,
            title=metadata.title,
            geography="United States",
            indicator="gdp",
            units=metadata.units,
            frequency=metadata.frequency,
            score=1.0,
            resolution_reason="Demo",
            source_url=metadata.source_url
        )

        # Perform vintage analysis
        print("🔄 Performing vintage analysis...")
        vintage_analysis = vintage_service.analyze_vintage_data(resolved_series, max_comparisons=5)

        print(f"   Analyzed {len(vintage_analysis.series_vintage_data)} series")
        print(f"   Generated {len(vintage_analysis.comparisons)} comparisons")
        print()

        # Show some examples of what users can now ask
        print("🎯 Example Queries Now Supported:")
        print()

        print("• 'What was the first-release value for Q4 2020 GDP?'")
        if vintage_dates:
            first_value = vintage_service.get_first_release_value(series_id, date(2010, 1, 1))
            print(f"  → First release value: {first_value}")
        print()

        print("• 'How much has the latest GDP data been revised from the original?'")
        if vintage_dates:
            comparison = vintage_service.compare_latest_vs_original(series_id, date(2010, 1, 1))
            if comparison:
                print(f"  → Original: {comparison['first_release_value']:.2f}")
                print(f"  → Latest: {comparison['latest_revision_value']:.2f}")
                print(f"  → Change: {comparison['percent_change']:+.2f}%")
        print()

        print("• 'Show me the revision history for the most recent GDP data'")
        latest_obs = client.get_series_observations(series_id, limit=1)
        if latest_obs:
            latest_date = latest_obs[0].date
            print(f"  → Latest observation date: {latest_date}")
            if vintage_dates:
                # Get what the value was on different vintage dates
                for vintage_date in vintage_dates[-3:]:  # Last 3 vintage dates
                    try:
                        obs_for_vintage = client.get_series_observations_for_vintage_date(
                            series_id, vintage_date
                        )
                        value_on_vintage = next(
                            (obs.value for obs in obs_for_vintage if obs.date == latest_date),
                            None
                        )
                        if value_on_vintage is not None:
                            print(f"    - As of {vintage_date}: {value_on_vintage:.2f}")
                    except Exception:
                        continue
        print()

        print("📈 Summary Statistics:")
        for stat_name, value in vintage_analysis.summary_stats.items():
            print(f"  • {stat_name}: {value:.4f}")

        print()
        print("✅ Vintage analysis functionality is now ready!")
        print("   Users can ask questions about data revisions and historical values.")

    except Exception as e:
        print(f"❌ Error during demo: {e}")
        print("\n💡 Tip: Make sure you have a valid FRED API key set in the FRED_API_KEY environment variable")


if __name__ == "__main__":
    demo_vintage_analysis()