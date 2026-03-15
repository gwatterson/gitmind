"""FastAPI application entrypoint — CORS, routers, startup/shutdown events."""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.models import init_db
from app.api.webhooks import router as webhooks_router
from app.api.reviews import router as reviews_router
from app.api.stream import router as stream_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init DB on startup."""
    log.info("app_starting", model=settings.GEMINI_MODEL)
    await init_db()
    log.info("database_initialized")
    yield
    log.info("app_shutting_down")


app = FastAPI(
    title="GitMind — Autonomous Code Review Agent",
    description="AI agent that analyzes GitHub Pull Requests for security, quality, and performance issues.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhooks_router)
app.include_router(reviews_router)
app.include_router(stream_router)


@app.get("/")
async def root():
    """Root endpoint — basic info."""
    return {
        "name": "GitMind",
        "description": "Autonomous Code Review Agent",
        "version": "1.0.0",
        "docs": "/docs",
    }
