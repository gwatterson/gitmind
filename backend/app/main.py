"""FastAPI application factory: middleware, routers, startup/shutdown events."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.api_keys import router as api_keys_router
from app.api.auth import router as auth_router
from app.api.llm import router as llm_router
from app.api.reviews import router as reviews_router
from app.api.stream import router as stream_router
from app.api.webhooks import router as webhooks_router
from app.config import settings
from app.core.errors import unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.ratelimit import limiter
from app.core.security import CSRF_HEADER
from app.db.models import init_db
from app.graph.prompts import prompt_versions
from app.llm import factory

configure_logging(settings.LOG_LEVEL, json_logs=settings.is_production)
log = structlog.get_logger()

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: init DB on startup."""
    log.info(
        "app_starting",
        environment=settings.ENVIRONMENT,
        auth_disabled=settings.AUTH_DISABLED,
    )
    if settings.AUTH_DISABLED:
        log.warning("auth_disabled", message="Every request is treated as an administrator")
    await init_db()
    await factory.load_runtime_provider()
    log.info(
        "database_initialized",
        llm_provider=factory.provider_name(),
        llm_model=factory.model_name(),
        # Loading the prompts here also fails fast on a malformed prompt file
        prompt_versions=prompt_versions(),
    )
    yield
    log.info("app_shutting_down")


async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


def create_app() -> FastAPI:
    # Interactive API docs are disabled in production
    docs_enabled = not settings.is_production
    app = FastAPI(
        title="GitMind: Autonomous Code Review Agent",
        description="AI agent that analyzes GitHub Pull Requests for security, quality, and performance issues.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.middleware("http")(add_security_headers)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", CSRF_HEADER],
    )

    app.include_router(auth_router)
    app.include_router(api_keys_router)
    app.include_router(llm_router)
    app.include_router(webhooks_router)
    app.include_router(reviews_router)
    app.include_router(stream_router)

    @app.get("/")
    @limiter.exempt
    async def root() -> dict[str, str | None]:
        """Root endpoint: basic info."""
        return {
            "name": "GitMind",
            "description": "Autonomous Code Review Agent",
            "version": "1.0.0",
            "docs": "/docs" if docs_enabled else None,
        }

    return app


app = create_app()
