from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.resolved_series import ResolvedSeries
from fred_query.schemas.vintage_analysis import (
    VintageAnalysisResult,
    VintageComparison,
    VintageObservation,
    VintageSeriesData,
)
from fred_query.services.fred_client import FREDClient


class VintageAnalysisService:
    """Service to perform vintage/revision analysis on FRED series data"""

    def __init__(self, fred_client: FREDClient):
        self.fred_client = fred_client

    def analyze_vintage_data(
        self,
        series: ResolvedSeries,
        vintage_limit: int = 100,
        max_comparisons: int = 10
    ) -> VintageAnalysisResult:
        """
        Analyze vintage data for a series to enable comparison of first-release vs. revised values

        Args:
            series: The series to analyze
            vintage_limit: Maximum number of vintage dates to retrieve
            max_comparisons: Maximum number of observation dates to compare across vintages

        Returns:
            VintageAnalysisResult containing comparison data
        """
        # Get all vintage dates for the series
        vintage_dates = self.fred_client.get_series_vintage_dates(series.series_id, limit=vintage_limit)

        if not vintage_dates:
            return VintageAnalysisResult()

        # Get observations for each vintage date
        all_vintage_observations: List[VintageObservation] = []

        # Limit vintage dates to avoid too many API calls
        vintage_dates_limited = vintage_dates[:min(10, len(vintage_dates))]

        for vintage_date in vintage_dates_limited:
            try:
                observations = self.fred_client.get_series_observations_for_vintage_date(
                    series.series_id, vintage_date
                )

                for obs in observations:
                    all_vintage_observations.append(
                        VintageObservation(
                            date=obs.date,
                            value=obs.value,
                            vintage_date=vintage_date
                        )
                    )
            except Exception:
                # Skip vintage dates that fail to load
                continue

        # Create vintage series data
        vintage_series_data = VintageSeriesData(
            series_id=series.series_id,
            title=series.title,
            vintage_observations=all_vintage_observations,
            vintage_dates=vintage_dates_limited
        )

        # Get current observations for comparison
        current_observations = self.fred_client.get_series_observations(series.series_id)
        current_values_map = {obs.date: obs.value for obs in current_observations}

        # Create comparisons for recent observation dates
        comparison_dates = sorted(current_values_map.keys(), reverse=True)[:max_comparisons]
        comparisons = []

        for obs_date in comparison_dates:
            first_value = vintage_series_data.get_first_release_value(obs_date)
            latest_value = vintage_series_data.get_latest_revision_value(obs_date)
            current_value = current_values_map.get(obs_date)

            # Get revision history for this date
            revision_history = vintage_series_data.get_revision_history(obs_date)

            # Calculate percent changes
            percent_change_from_first = None
            if first_value is not None and first_value != 0:
                percent_change_from_first = ((current_value or 0) - first_value) / abs(first_value) * 100

            percent_change_from_latest = None
            if latest_value is not None and latest_value != 0:
                percent_change_from_latest = ((current_value or 0) - latest_value) / abs(latest_value) * 100

            comparison = VintageComparison(
                series_id=series.series_id,
                observation_date=obs_date,
                first_release_value=first_value,
                latest_revision_value=latest_value,
                current_value=current_value,
                revision_count=len(revision_history),
                revision_history=revision_history,
                percent_change_from_first=percent_change_from_first,
                percent_change_from_latest=percent_change_from_latest
            )
            comparisons.append(comparison)

        # Calculate summary statistics
        summary_stats = self._calculate_summary_stats(comparisons)

        return VintageAnalysisResult(
            series_vintage_data=[vintage_series_data],
            comparisons=comparisons,
            summary_stats=summary_stats
        )

    def _calculate_summary_stats(self, comparisons: List[VintageComparison]) -> Dict[str, float]:
        """Calculate summary statistics for the vintage analysis"""
        stats = {}

        # Calculate average revision impact
        percent_changes = [
            comp.percent_change_from_first
            for comp in comparisons
            if comp.percent_change_from_first is not None
        ]

        if percent_changes:
            avg_change = sum(percent_changes) / len(percent_changes)
            stats["average_revision_impact_pct"] = avg_change
            stats["total_comparisons"] = len(comparisons)
            stats["comparisons_with_data"] = len(percent_changes)

        return stats

    def get_first_release_value(self, series_id: str, obs_date: date) -> Optional[float]:
        """Get the first-release value for a specific series and observation date"""
        vintage_dates = self.fred_client.get_series_vintage_dates(series_id, limit=100)
        if not vintage_dates:
            return None

        first_vintage = min(vintage_dates)
        try:
            observations = self.fred_client.get_series_observations_for_vintage_date(
                series_id, first_vintage
            )
            for obs in observations:
                if obs.date == obs_date:
                    return obs.value
        except Exception:
            pass

        return None

    def compare_latest_vs_original(self, series_id: str, obs_date: date) -> Optional[Dict[str, float]]:
        """Compare latest revision vs original release for a specific observation date"""
        vintage_dates = self.fred_client.get_series_vintage_dates(series_id, limit=100)
        if not vintage_dates:
            return None

        first_vintage = min(vintage_dates)
        latest_vintage = max(vintage_dates)

        first_value = None
        latest_value = None

        # Get first release value
        try:
            first_observations = self.fred_client.get_series_observations_for_vintage_date(
                series_id, first_vintage
            )
            for obs in first_observations:
                if obs.date == obs_date:
                    first_value = obs.value
                    break
        except Exception:
            pass

        # Get latest revision value
        try:
            latest_observations = self.fred_client.get_series_observations_for_vintage_date(
                series_id, latest_vintage
            )
            for obs in latest_observations:
                if obs.date == obs_date:
                    latest_value = obs.value
                    break
        except Exception:
            pass

        if first_value is not None and latest_value is not None:
            percent_change = ((latest_value - first_value) / abs(first_value)) * 100 if first_value != 0 else 0
            return {
                "first_release_value": first_value,
                "latest_revision_value": latest_value,
                "percent_change": percent_change
            }

        return None