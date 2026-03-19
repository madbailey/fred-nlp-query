from __future__ import annotations

from datetime import date
import unittest

from fastapi.testclient import TestClient

from fred_query.api.app import (
    app,
    get_natural_language_query_service,
    get_state_gdp_comparison_service,
)
from fred_query.errors import ConfigurationError
from fred_query.schemas.analysis import (
    AnalysisResult,
    QueryResponse,
    RoutedQueryResponse,
    RoutedQueryStatus,
    SeriesAnalysis,
)
from fred_query.schemas.chart import AxisSpec, ChartSpec, ChartTrace
from fred_query.schemas.intent import ComparisonMode, Geography, GeographyType, QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesSearchMatch
from fred_query.services import FREDAPIError, QuerySession


def _build_query_response() -> QueryResponse:
    california = ResolvedSeries(
        series_id="CARGSP",
        title="Real GDP: California",
        geography="California",
        indicator="real_gdp",
        units="Millions of Chained 2017 Dollars",
        frequency="A",
        seasonal_adjustment="NSA",
        resolution_reason="fixture",
        source_url="https://fred.stlouisfed.org/series/CARGSP",
    )
    texas = ResolvedSeries(
        series_id="TXRGSP",
        title="Real GDP: Texas",
        geography="Texas",
        indicator="real_gdp",
        units="Millions of Chained 2017 Dollars",
        frequency="A",
        seasonal_adjustment="NSA",
        resolution_reason="fixture",
        source_url="https://fred.stlouisfed.org/series/TXRGSP",
    )
    intent = QueryIntent(
        task_type=TaskType.STATE_GDP_COMPARISON,
        geographies=[
            Geography(name="California", geography_type=GeographyType.STATE),
            Geography(name="Texas", geography_type=GeographyType.STATE),
        ],
        comparison_mode=ComparisonMode.STATE_VS_STATE,
        start_date=date(2019, 1, 1),
        transform=TransformType.NORMALIZED_INDEX,
        normalization=True,
    )
    return QueryResponse(
        intent=intent,
        analysis=AnalysisResult(
            series_results=[
                SeriesAnalysis(series=california, latest_value=1.0, latest_observation_date=date(2024, 1, 1)),
                SeriesAnalysis(series=texas, latest_value=1.0, latest_observation_date=date(2024, 1, 1)),
            ],
            coverage_start=date(2019, 1, 1),
            coverage_end=date(2024, 1, 1),
            latest_observation_date=date(2024, 1, 1),
        ),
        chart=ChartSpec(
            title="Real GDP Comparison: California vs Texas",
            subtitle="Fixture",
            x_axis=AxisSpec(title="Date"),
            y_axis=AxisSpec(title="Index (Base = 100)"),
            series=[
                ChartTrace(name="California", x=[date(2019, 1, 1)], y=[100.0]),
                ChartTrace(name="Texas", x=[date(2019, 1, 1)], y=[100.0]),
            ],
            source_note="Source: FRED, Federal Reserve Bank of St. Louis",
        ),
        answer_text="Completed comparison.",
    )


class _FakeNaturalLanguageQueryService:
    def __init__(self, response: RoutedQueryResponse) -> None:
        self.response = response
        self.last_call: tuple[str, str | None, list[str | None] | None, QuerySession | None] | None = None

    def ask(
        self,
        query: str,
        *,
        selected_series_id: str | None = None,
        selected_series_ids: list[str | None] | None = None,
        session_context: QuerySession | None = None,
    ) -> RoutedQueryResponse:
        session_snapshot = None
        if session_context is not None:
            session_snapshot = QuerySession(
                session_id=session_context.session_id,
                created_at=session_context.created_at,
                updated_at=session_context.updated_at,
                last_query=session_context.last_query,
                last_response=session_context.last_response,
            )
        self.last_call = (query, selected_series_id, selected_series_ids, session_snapshot)
        return self.response


class _FakeStateGDPComparisonService:
    def compare(self, **_: object) -> QueryResponse:
        return _build_query_response()


class _FailingNaturalLanguageQueryService:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def ask(
        self,
        query: str,
        *,
        selected_series_id: str | None = None,
        selected_series_ids: list[str | None] | None = None,
        session_context: QuerySession | None = None,
    ) -> RoutedQueryResponse:
        raise self.exc


class _FailingStateGDPComparisonService:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def compare(self, **_: object) -> QueryResponse:
        raise self.exc


class APITest(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_index(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Ask a question about the economy.", response.text)

    def test_static_assets(self) -> None:
        js_response = self.client.get("/static/app.js")
        css_response = self.client.get("/static/styles.css")

        self.assertEqual(js_response.status_code, 200)
        self.assertIn("javascript", js_response.headers["content-type"])
        self.assertIn("handleSubmit", js_response.text)
        self.assertEqual(css_response.status_code, 200)
        self.assertIn("text/css", css_response.headers["content-type"])
        self.assertIn(".hero", css_response.text)

    def test_ask_completed(self) -> None:
        routed = RoutedQueryResponse(
            status=RoutedQueryStatus.COMPLETED,
            intent=_build_query_response().intent,
            answer_text="Completed comparison.",
            query_response=_build_query_response(),
        )
        app.dependency_overrides[get_natural_language_query_service] = lambda: _FakeNaturalLanguageQueryService(routed)

        response = self.client.post("/api/ask", json={"query": "Compare California and Texas GDP"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["session_id"])
        self.assertEqual(payload["plotly_figure"]["layout"]["title"]["text"], "Real GDP Comparison: California vs Texas")

    def test_ask_forwards_selected_series_id(self) -> None:
        routed = RoutedQueryResponse(
            status=RoutedQueryStatus.COMPLETED,
            intent=_build_query_response().intent,
            answer_text="Completed comparison.",
            query_response=_build_query_response(),
        )
        service = _FakeNaturalLanguageQueryService(routed)
        app.dependency_overrides[get_natural_language_query_service] = lambda: service

        response = self.client.post(
            "/api/ask",
            json={"query": "Show inflation", "selected_series_id": "CPIAUCSL"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.last_call[:3], ("Show inflation", "CPIAUCSL", ["CPIAUCSL"]))
        self.assertIsNotNone(service.last_call[3])

    def test_ask_forwards_selected_series_ids(self) -> None:
        routed = RoutedQueryResponse(
            status=RoutedQueryStatus.COMPLETED,
            intent=_build_query_response().intent,
            answer_text="Completed comparison.",
            query_response=_build_query_response(),
        )
        service = _FakeNaturalLanguageQueryService(routed)
        app.dependency_overrides[get_natural_language_query_service] = lambda: service

        response = self.client.post(
            "/api/ask",
            json={"query": "Compare oil and inflation", "selected_series_ids": [None, "CPIAUCSL"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.last_call[:3], ("Compare oil and inflation", None, [None, "CPIAUCSL"]))
        self.assertIsNotNone(service.last_call[3])

    def test_ask_clarification(self) -> None:
        routed = RoutedQueryResponse(
            status=RoutedQueryStatus.NEEDS_CLARIFICATION,
            intent=QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                clarification_needed=True,
                clarification_question="Do you mean CPI or PCE inflation?",
            ),
            answer_text="Do you mean CPI or PCE inflation?",
            candidate_series=[
                SeriesSearchMatch(
                    series_id="CPIAUCSL",
                    title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                    source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
                )
            ],
        )
        app.dependency_overrides[get_natural_language_query_service] = lambda: _FakeNaturalLanguageQueryService(routed)

        response = self.client.post("/api/ask", json={"query": "Show inflation"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "needs_clarification")
        self.assertTrue(payload["session_id"])
        self.assertEqual(payload["candidate_series"][0]["series_id"], "CPIAUCSL")

    def test_ask_reuses_session_id_for_follow_up(self) -> None:
        routed = RoutedQueryResponse(
            status=RoutedQueryStatus.COMPLETED,
            intent=_build_query_response().intent,
            answer_text="Completed comparison.",
            query_response=_build_query_response(),
        )
        service = _FakeNaturalLanguageQueryService(routed)
        app.dependency_overrides[get_natural_language_query_service] = lambda: service

        first = self.client.post("/api/ask", json={"query": "Show inflation"})

        self.assertEqual(first.status_code, 200)
        session_id = first.json()["session_id"]
        self.assertTrue(session_id)

        second = self.client.post(
            "/api/ask",
            json={"query": "Now make that YoY", "session_id": session_id},
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["session_id"], session_id)
        self.assertIsNotNone(service.last_call)
        self.assertIsNotNone(service.last_call[3])
        self.assertEqual(service.last_call[3].session_id, session_id)
        self.assertEqual(service.last_call[3].last_query, "Show inflation")

    def test_compare_state_gdp(self) -> None:
        app.dependency_overrides[get_state_gdp_comparison_service] = lambda: _FakeStateGDPComparisonService()

        response = self.client.post(
            "/api/compare/state-gdp",
            json={
                "state1": "California",
                "state2": "Texas",
                "start_date": "2019-01-01",
                "normalize": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer_text"], "Completed comparison.")
        self.assertEqual(payload["plotly_figure"]["layout"]["title"]["text"], "Real GDP Comparison: California vs Texas")

    def test_ask_blank_query_returns_validation_error(self) -> None:
        response = self.client.post("/api/ask", json={"query": "   "})

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertIn("Query must not be blank", payload["detail"][0]["msg"])

    def test_compare_state_gdp_rejects_invalid_date_range(self) -> None:
        response = self.client.post(
            "/api/compare/state-gdp",
            json={
                "state1": "California",
                "state2": "Texas",
                "start_date": "2020-01-01",
                "end_date": "2019-01-01",
                "normalize": True,
            },
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertIn("end_date must be on or after start_date", payload["detail"][0]["msg"])

    def test_ask_value_error_returns_json_400(self) -> None:
        app.dependency_overrides[get_natural_language_query_service] = (
            lambda: _FailingNaturalLanguageQueryService(ValueError("No deterministic execution path matched the request."))
        )

        response = self.client.post("/api/ask", json={"query": "Compare GDP"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("application/json", response.headers["content-type"])
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["detail"], "No deterministic execution path matched the request.")

    def test_compare_state_gdp_upstream_error_returns_json_502(self) -> None:
        app.dependency_overrides[get_state_gdp_comparison_service] = (
            lambda: _FailingStateGDPComparisonService(FREDAPIError("FRED request timed out."))
        )

        response = self.client.post(
            "/api/compare/state-gdp",
            json={
                "state1": "California",
                "state2": "Texas",
                "start_date": "2019-01-01",
                "normalize": True,
            },
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("application/json", response.headers["content-type"])
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "fred_error")
        self.assertEqual(payload["detail"], "FRED request timed out.")

    def test_ask_configuration_error_returns_json_503(self) -> None:
        app.dependency_overrides[get_natural_language_query_service] = (
            lambda: _FailingNaturalLanguageQueryService(ConfigurationError("An OpenAI API key is required for intent parsing."))
        )

        response = self.client.post("/api/ask", json={"query": "Show me unemployment"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("application/json", response.headers["content-type"])
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "service_configuration_error")
        self.assertEqual(payload["detail"], "An OpenAI API key is required for intent parsing.")


if __name__ == "__main__":
    unittest.main()
