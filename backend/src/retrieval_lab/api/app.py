from __future__ import annotations

import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from retrieval_lab.api.deps import RunScheduler, require_token
from retrieval_lab.api.routers import configs, golden, judge, query, runs, system
from retrieval_lab.api.schemas import ErrorBody, ErrorResponse
from retrieval_lab.container import Container, build_container
from retrieval_lab.db.session import transaction
from retrieval_lab.errors import RetrievalLabError
from retrieval_lab.log import configure_logging, get_logger
from retrieval_lab.repositories.runs import RunRepository
from retrieval_lab.settings import Settings, get_settings

log = get_logger(__name__)

_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def _error(
    status_code: int, code: str, message: str, details: list[dict[str, object]] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body, exclude_none=True))


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RetrievalLabError)
    async def domain_error(_: Request, exc: RetrievalLabError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return _error(422, "validation_failed", "Request validation failed", details)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        log.warning("integrity_error", error=str(exc.orig))
        return _error(409, "conflict", "The change conflicts with existing data; retry the request")


async def _request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        # Handled here rather than by an Exception handler, which Starlette runs outside every
        # middleware: this way a 500 still carries the request id and CORS headers.
        log.exception("unhandled_error", error=type(exc).__name__)
        response = _error(500, "internal_error", "Something went wrong on our side")
    finally:
        structlog.contextvars.unbind_contextvars("request_id")
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    if request.url.path != "/api/health":
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=round(elapsed, 1),
            request_id=request_id,
        )
    return response


async def _reconcile_interrupted_runs(container: Container) -> None:
    async with transaction(container.sessions) as session:
        count = await RunRepository(session).fail_interrupted(trigger="api")
    if count:
        log.warning("interrupted_runs_marked_failed", count=count)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.container = container or build_container(settings)
        app.state.scheduler = RunScheduler(app.state.container, settings.max_active_runs)
        await _reconcile_interrupted_runs(app.state.container)
        log.info("api_started", offline=settings.offline, auth=settings.api_token is not None)
        try:
            yield
        finally:
            await app.state.scheduler.shutdown()
            if container is None:
                await app.state.container.aclose()

    app = FastAPI(
        title="Retrieval Lab API",
        version="0.1.0",
        description="Hybrid retrieval, grounded answers and the evaluation harness behind them.",
        lifespan=lifespan,
        dependencies=[Depends(require_token)],
    )
    # Middleware added last runs first, so CORS wraps the request context and sees its 500s.
    app.middleware("http")(_request_context)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["authorization", "content-type", "x-request-id"],
        expose_headers=["x-request-id"],
    )
    _install_error_handlers(app)
    for router in (system.router, configs.router, query.router, golden.router, runs.router, judge.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
