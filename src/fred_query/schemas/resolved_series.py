from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClarificationBadge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    label: str


class ClarificationOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str | None = None
    title: str | None = None
    hint: str | None = None
    badges: list[ClarificationBadge] = Field(default_factory=list)


class SeriesSearchMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series_id: str
    title: str
    clarification_option: ClarificationOption | None = None
    selection_label: str | None = None
    selection_hint: str | None = None
    selection_badges: list[str] = Field(default_factory=list)
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
