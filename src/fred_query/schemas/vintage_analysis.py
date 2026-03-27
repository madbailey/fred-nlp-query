from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from fred_query.schemas.analysis import ObservationPoint


class VintageObservation(BaseModel):
    """Represents a single observation value at a specific vintage date"""
    model_config = ConfigDict(extra="ignore")

    date: date
    value: float
    vintage_date: date


class VintageSeriesData(BaseModel):
    """Holds vintage data for a single series across multiple vintage dates"""
    model_config = ConfigDict(extra="ignore")

    series_id: str
    title: str
    vintage_observations: List[VintageObservation] = []
    vintage_dates: List[date] = []

    def get_first_release_value(self, obs_date: date) -> Optional[float]:
        """Get the first-release value for a specific observation date"""
        first_vintage = min(self.vintage_dates) if self.vintage_dates else None
        if not first_vintage:
            return None

        for obs in self.vintage_observations:
            if obs.date == obs_date and obs.vintage_date == first_vintage:
                return obs.value
        return None

    def get_latest_revision_value(self, obs_date: date) -> Optional[float]:
        """Get the latest revision value for a specific observation date"""
        latest_vintage = max(self.vintage_dates) if self.vintage_dates else None
        if not latest_vintage:
            return None

        for obs in reversed(self.vintage_observations):
            if obs.date == obs_date and obs.vintage_date == latest_vintage:
                return obs.value
        return None

    def get_revision_history(self, obs_date: date) -> List[VintageObservation]:
        """Get all revisions for a specific observation date, ordered by vintage date"""
        revisions = [obs for obs in self.vintage_observations if obs.date == obs_date]
        revisions.sort(key=lambda x: x.vintage_date)
        return revisions


class VintageComparison(BaseModel):
    """Comparison between different vintages of the same data"""
    model_config = ConfigDict(extra="ignore")

    series_id: str
    observation_date: date
    first_release_value: Optional[float] = None
    latest_revision_value: Optional[float] = None
    current_value: Optional[float] = None  # Value as of today
    revision_count: int = 0
    revision_history: List[VintageObservation] = []
    percent_change_from_first: Optional[float] = None
    percent_change_from_latest: Optional[float] = None


class VintageAnalysisResult(BaseModel):
    """Complete vintage analysis result for one or more series"""
    model_config = ConfigDict(extra="ignore")

    series_vintage_data: List[VintageSeriesData] = []
    comparisons: List[VintageComparison] = []
    summary_stats: Dict[str, float] = {}

    def get_series_vintage_data(self, series_id: str) -> Optional[VintageSeriesData]:
        """Get vintage data for a specific series"""
        for data in self.series_vintage_data:
            if data.series_id == series_id:
                return data
        return None