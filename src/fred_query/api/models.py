from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fred_query.schemas.analysis import QueryResponse, RoutedQueryResponse, RoutedQueryStatus
from fred_query.schemas.intent import QueryIntent
from fred_query.schemas.resolved_series import SeriesSearchMatch


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str


class StateGDPCompareRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state1: str
    state2: str
    start_date: date
    end_date: date | None = None
    normalize: bool = True


class ApiQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer_text: str
    result: QueryResponse
    plotly_figure: dict[str, Any]

    @classmethod
    def from_query_response(cls, response: QueryResponse) -> "ApiQueryResponse":
        return cls(
            answer_text=response.answer_text,
            result=response,
            plotly_figure=response.chart.to_plotly_dict(),
        )


class ApiRoutedQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: RoutedQueryStatus
    answer_text: str
    intent: QueryIntent
    candidate_series: list[SeriesSearchMatch] = Field(default_factory=list)
    result: QueryResponse | None = None
    plotly_figure: dict[str, Any] | None = None

    @classmethod
    def from_routed_response(cls, response: RoutedQueryResponse) -> "ApiRoutedQueryResponse":
        return cls(
            status=response.status,
            answer_text=response.answer_text,
            intent=response.intent,
            candidate_series=response.candidate_series,
            result=response.query_response,
            plotly_figure=response.query_response.chart.to_plotly_dict() if response.query_response else None,
        )
