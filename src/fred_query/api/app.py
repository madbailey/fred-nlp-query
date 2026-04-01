from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
import logging
from pathlib import Path
from typing import Any, TypeVar

from fastapi import Body, Depends, FastAPI, Request, Response, status
from fastapi.dependencies.utils import get_dependant, solve_dependencies
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from fred_query.errors import ConfigurationError, UpstreamServiceError
from fred_query.api.models import ApiQueryResponse, ApiRoutedQueryResponse, AskRequest, StateGDPCompareRequest
from fred_query.config import Settings, get_settings
from fred_query.services import (
    FREDClient,
    NaturalLanguageQueryService,
    OpenAIIntentParser,
    QuerySessionService,
    StateGDPComparisonService,
)

STATIC_DIR = Path(__file__).parent / "static"
LOGGER = logging.getLogger(__name__)
QUERY_SESSION_SERVICE = QuerySessionService()
T = TypeVar("T")


def get_app_settings() -> Settings:
    return get_settings()


def get_fred_client(settings: Settings = Depends(get_app_settings)) -> Iterator[FREDClient]:
    client = _create_fred_client(settings)
    try:
        yield client
    finally:
        client.close()


def _create_fred_client(settings: Settings) -> FREDClient:
    return FREDClient(
        api_key=settings.fred_api_key or "",
        base_url=settings.fred_base_url,
        timeout_seconds=settings.http_timeout_seconds,
    )


def _create_natural_language_query_service(settings: Settings, fred_client: FREDClient) -> NaturalLanguageQueryService:
    parser = OpenAIIntentParser(
        api_key=settings.openai_api_key or "",
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
    )
    return NaturalLanguageQueryService(
        parser=parser,
        fred_client=fred_client,
    )


def get_natural_language_query_service(
    settings: Settings = Depends(get_app_settings),
    fred_client: FREDClient = Depends(get_fred_client),
) -> NaturalLanguageQueryService:
    return _create_natural_language_query_service(settings, fred_client)


def get_state_gdp_comparison_service(
    fred_client: FREDClient = Depends(get_fred_client),
) -> StateGDPComparisonService:
    return StateGDPComparisonService(fred_client)


def get_query_session_service() -> QuerySessionService:
    return QUERY_SESSION_SERVICE


def _validate_request_model(model_type: type[T], payload: Any) -> T:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(), body=payload) from exc


async def _resolve_natural_language_query_service(
    service: NaturalLanguageQueryService = Depends(get_natural_language_query_service),
) -> NaturalLanguageQueryService:
    return service


async def _resolve_state_gdp_comparison_service(
    service: StateGDPComparisonService = Depends(get_state_gdp_comparison_service),
) -> StateGDPComparisonService:
    return service


@asynccontextmanager
async def _managed_dependency(
    request: Request,
    dependency: Callable[..., Any],
    *,
    value_name: str,
) -> AsyncIterator[Any]:
    dependant = get_dependant(path=request.scope["path"], call=dependency)
    async with AsyncExitStack() as async_exit_stack:
        solved = await solve_dependencies(
            request=request,
            dependant=dependant,
            body=None,
            background_tasks=None,
            response=Response(),
            dependency_overrides_provider=request.app,
            dependency_cache=None,
            async_exit_stack=async_exit_stack,
            embed_body_fields=False,
        )
        if solved.errors:
            raise RequestValidationError(solved.errors)
        yield solved.values[value_name]


def create_app() -> FastAPI:
    app = FastAPI(
        title="FRED Query API",
        version="0.1.0",
        description="Natural-language FRED query backend with deterministic execution and plot-ready responses.",
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def error_payload(*, code: str, message: str) -> dict[str, object]:
        return {
            "detail": message,
            "error": {
                "code": code,
                "message": message,
            },
        }

    @app.exception_handler(ConfigurationError)
    async def configuration_error_handler(_: Request, exc: ConfigurationError) -> JSONResponse:
        LOGGER.warning("Configuration error while serving request: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_payload(code="service_configuration_error", message=str(exc)),
        )

    @app.exception_handler(UpstreamServiceError)
    async def upstream_service_error_handler(_: Request, exc: UpstreamServiceError) -> JSONResponse:
        LOGGER.warning("Upstream service error from %s: %s", exc.service, exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=error_payload(code=f"{exc.service}_error", message=str(exc)),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        LOGGER.info("Invalid request rejected: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_payload(code="invalid_request", message=str(exc)),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled request error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(
                code="internal_server_error",
                message="The server hit an unexpected error while processing the request.",
            ),
        )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/ask", response_model=ApiRoutedQueryResponse)
    async def ask(
        http_request: Request,
        payload: dict[str, Any] = Body(...),
        query_session_service: QuerySessionService = Depends(get_query_session_service),
    ) -> ApiRoutedQueryResponse:
        request = _validate_request_model(AskRequest, payload)
        session = query_session_service.get_or_create(request.session_id)
        session_context = query_session_service.get_context(
            session_id=session.session_id,
            revision_id=request.base_revision_id,
        )
        async with _managed_dependency(
            http_request,
            _resolve_natural_language_query_service,
            value_name="service",
        ) as service:
            response = service.ask(
                request.query,
                selected_series_id=request.selected_series_id,
                selected_series_ids=request.selected_series_ids,
                session_context=session_context,
            )
        stored_session, revision = query_session_service.store_turn(
            session_id=session.session_id,
            query=request.query,
            response=response,
        )
        return ApiRoutedQueryResponse.from_routed_response(
            response,
            session_id=stored_session.session_id,
            revision_id=revision.revision_id,
        )

    @app.post("/api/compare/state-gdp", response_model=ApiQueryResponse)
    async def compare_state_gdp(
        http_request: Request,
        payload: dict[str, Any] = Body(...),
    ) -> ApiQueryResponse:
        request = _validate_request_model(StateGDPCompareRequest, payload)
        async with _managed_dependency(
            http_request,
            _resolve_state_gdp_comparison_service,
            value_name="service",
        ) as service:
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
