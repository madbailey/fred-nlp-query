from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI

from fred_query.api.models import ApiQueryResponse, ApiRoutedQueryResponse, AskRequest, StateGDPCompareRequest
from fred_query.config import Settings, get_settings
from fred_query.services import FREDClient, NaturalLanguageQueryService, OpenAIIntentParser, StateGDPComparisonService


def get_app_settings() -> Settings:
    return get_settings()


def get_fred_client(settings: Settings = Depends(get_app_settings)) -> Iterator[FREDClient]:
    client = FREDClient(
        api_key=settings.fred_api_key or "",
        base_url=settings.fred_base_url,
        timeout_seconds=settings.http_timeout_seconds,
    )
    try:
        yield client
    finally:
        client.close()


def get_natural_language_query_service(
    settings: Settings = Depends(get_app_settings),
    fred_client: FREDClient = Depends(get_fred_client),
) -> NaturalLanguageQueryService:
    parser = OpenAIIntentParser(
        api_key=settings.openai_api_key or "",
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
    )
    return NaturalLanguageQueryService(
        parser=parser,
        fred_client=fred_client,
    )


def get_state_gdp_comparison_service(
    fred_client: FREDClient = Depends(get_fred_client),
) -> StateGDPComparisonService:
    return StateGDPComparisonService(fred_client)


def create_app() -> FastAPI:
    app = FastAPI(
        title="FRED Query API",
        version="0.1.0",
        description="Natural-language FRED query backend with deterministic execution and plot-ready responses.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/ask", response_model=ApiRoutedQueryResponse)
    def ask(
        request: AskRequest,
        service: NaturalLanguageQueryService = Depends(get_natural_language_query_service),
    ) -> ApiRoutedQueryResponse:
        response = service.ask(request.query)
        return ApiRoutedQueryResponse.from_routed_response(response)

    @app.post("/api/compare/state-gdp", response_model=ApiQueryResponse)
    def compare_state_gdp(
        request: StateGDPCompareRequest,
        service: StateGDPComparisonService = Depends(get_state_gdp_comparison_service),
    ) -> ApiQueryResponse:
        response = service.compare(
            state1=request.state1,
            state2=request.state2,
            start_date=request.start_date,
            end_date=request.end_date,
            normalize=request.normalize,
        )
        return ApiQueryResponse.from_query_response(response)

    return app


app = create_app()
