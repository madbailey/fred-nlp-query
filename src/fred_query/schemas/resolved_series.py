from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SeriesSearchMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series_id: str
    title: str
    units: str | None = None
    frequency: str | None = None
    seasonal_adjustment: str | None = None
    notes: str | None = None
    popularity: int | None = None
    source_url: str


class SeriesMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series_id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str | None = None
    notes: str | None = None
    source_url: str


class ResolvedSeries(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series_id: str
    title: str
    geography: str
    indicator: str
    units: str
    frequency: str
    seasonal_adjustment: str | None = None
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    resolution_reason: str
    source_url: str
