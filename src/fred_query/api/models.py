from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from fred_query.api.follow_up_suggestions import build_follow_up_suggestions
from fred_query.schemas.analysis import (
    FollowUpSuggestion,
    QueryResponse,
    RoutedQueryReason,
    RoutedQueryResponse,
    RoutedQueryStatus,
)
from fred_query.schemas.intent import QueryIntent
from fred_query.schemas.resolved_series import SeriesSearchMatch


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    session_id: str | None = None
    base_revision_id: str | None = None
    selected_series_id: str | None = None
    selected_series_ids: list[str | None] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Query must not be blank.")
        return stripped

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("base_revision_id")
    @classmethod
    def validate_base_revision_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("selected_series_id")
    @classmethod
    def validate_selected_series_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("selected_series_ids")
    @classmethod
    def validate_selected_series_ids(cls, value: list[str | None]) -> list[str | None]:
        normalized: list[str | None] = []
        for item in value:
            if item is None:
                normalized.append(None)
                continue
            stripped = item.strip()
            normalized.append(stripped or None)
        return normalized

    @model_validator(mode="after")
    def normalize_selected_series_inputs(self) -> "AskRequest":
        if self.selected_series_id and not self.selected_series_ids:
            self.selected_series_ids = [self.selected_series_id]
        return self


class StateGDPCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state1: str
    state2: str
    start_date: date
    end_date: date | None = None
    normalize: StrictBool = True

    @field_validator("state1", "state2")
    @classmethod
    def validate_state_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("State names must not be blank.")
        return stripped

    @model_validator(mode="after")
    def validate_date_range(self) -> "StateGDPCompareRequest":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class ApiQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer_text: str
    result: QueryResponse
    plotly_figure: dict[str, Any]
    follow_up_suggestions: list[FollowUpSuggestion] = Field(default_factory=list)

    @classmethod
    def from_query_response(cls, response: QueryResponse) -> "ApiQueryResponse":
        return cls(
            answer_text=response.answer_text,
            result=response,
            plotly_figure=response.chart.to_plotly_dict(),
            follow_up_suggestions=build_follow_up_suggestions(response),
        )


class ApiRoutedQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    revision_id: str
    status: RoutedQueryStatus
    reason: RoutedQueryReason | None = None
    answer_text: str
    intent: QueryIntent
    candidate_series: list[SeriesSearchMatch] = Field(default_factory=list)
    result: QueryResponse | None = None
    plotly_figure: dict[str, Any] | None = None
    follow_up_suggestions: list[FollowUpSuggestion] = Field(default_factory=list)

    @classmethod
    def from_routed_response(
        cls,
        response: RoutedQueryResponse,
        *,
        session_id: str,
        revision_id: str,
    ) -> "ApiRoutedQueryResponse":
        return cls(
            session_id=session_id,
            revision_id=revision_id,
            status=response.status,
            reason=response.reason,
            answer_text=response.answer_text,
            intent=response.intent,
            candidate_series=response.candidate_series,
            result=response.query_response,
            plotly_figure=response.query_response.chart.to_plotly_dict() if response.query_response else None,
            follow_up_suggestions=(
                build_follow_up_suggestions(response.query_response)
                if response.query_response is not None
                else []
            ),
        )
