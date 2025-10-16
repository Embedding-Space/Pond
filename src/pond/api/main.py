"""Main FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import REGISTRY, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator

from pond.domain import MemoryRepository
from pond.infrastructure.auth import APIKeyManager
from pond.infrastructure.database import DatabasePool
from pond.startup_check import check_configuration, run_startup_checks

from .middleware import (
    AuthenticationMiddleware,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
)

# Configure structlog for our app only
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Run comprehensive startup checks (vital signs only)
    if not await run_startup_checks():
        # Startup checks failed - exit cleanly
        print("\nStartup failed. Exiting.\n", flush=True)
        import sys
        sys.exit(1)

    # Run legacy configuration check
    check_configuration()

    # Initialize database pool
    logger.info("initializing_database_pool")
    app.state.db_pool = DatabasePool()
    await app.state.db_pool.initialize()
    logger.info("database_pool_ready")

    # Initialize API key manager
    app.state.api_key_manager = APIKeyManager(app.state.db_pool)

    # Initialize singleton MemoryRepository
    logger.info("initializing_memory_repository")
    app.state.memory_repository = MemoryRepository(app.state.db_pool)
    logger.info(
        "memory_repository_ready",
        spacy_model_loaded=bool(app.state.memory_repository._nlp),
    )

    # API key authentication is always required
    logger.info("API key authentication required for all endpoints")

    yield

    # Cleanup
    logger.info("closing_database_pool")
    await app.state.db_pool.close()


# Create v1 API app
api_v1 = FastAPI(
    title="Pond API v1",
    description="Semantic memory system for AI assistants",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Include v1 routes
from .routes import health, memories  # noqa: E402

api_v1.include_router(health.router)
api_v1.include_router(memories.router)

# Create main app and mount v1
app = FastAPI(
    title="Pond",
    description="Semantic memory system for AI assistants",
    lifespan=lifespan,
    docs_url=None,  # Disable docs at root
    openapi_url=None,  # Disable openapi at root
    redoc_url=None,  # Disable redoc at root
)

# Mount v1 API
# Share the main app's state with the sub-app
api_v1.state = app.state
app.mount("/api/v1", api_v1)

# Add middleware to main app
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

# Add Prometheus instrumentation for automatic HTTP metrics
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=True,  # Respects ENABLE_METRICS env var
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],  # Don't track metrics endpoint itself
    env_var_name="ENABLE_METRICS",
    inprogress_name="pond_http_requests_inprogress",
    inprogress_labels=True,
)

# Instrument the app for automatic HTTP metrics
instrumentator.instrument(app)


# Add metrics endpoint manually to ensure it's accessible
@app.get("/metrics", include_in_schema=False)
async def get_metrics() -> Response:
    """Prometheus metrics endpoint."""
    metrics = generate_latest(REGISTRY)
    return Response(content=metrics, media_type="text/plain; version=0.0.4")


# Secret Easter egg: THE VISUALIZER
# Check if the built visualizer exists
visualizer_dist = Path(__file__).parent.parent.parent.parent / "web" / "dist"
if visualizer_dist.exists():
    # Serve static files for assets
    app.mount("/assets", StaticFiles(directory=visualizer_dist / "assets"), name="assets")

    # Serve index.html at root
    @app.get("/", include_in_schema=False)
    async def serve_visualizer():
        """Secret visualizer at root URL."""
        return FileResponse(visualizer_dist / "index.html")
