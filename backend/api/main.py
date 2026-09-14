import asyncio
import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.error_handler import register_exception_handlers
from backend.core.log_redaction import redact_url
from backend.core.logging import setup_logging
from backend.core.storage import object_storage
from backend.db.session import SessionLocal, engine
from backend.modules.ai.providers import close_ai_provider_http_clients
from backend.modules.memory.infrastructure.memory_config import validate_memory_config
from backend.modules.platform.service import PlatformService
from backend.modules.rag.infrastructure.rag_config import validate_rag_config
from backend.observability import setup_observability
from backend.observability.prometheus_metrics import startup_dependency_duration_seconds
from backend.observability.service import close_observability_http_client
from backend.workers.async_dispatch import log_eager_mode_startup_warning
from backend.workers.readiness import worker_readiness

from backend.api.middleware.correlation_id import CorrelationIdMiddleware
from backend.api.middleware.csrf import CSRFMiddleware
from backend.api.middleware.public_rate_limit import PublicRateLimitMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.api.middleware.security_headers import SecurityHeadersMiddleware
from backend.observability.request_diagnostics import (
    DIAGNOSTICS_HEADER,
    TRACE_ID_HEADER,
)
from backend.modules.developer_diagnostics.middleware import DeveloperDiagnosticsMiddleware
from .router import api_router
from .v1.health import health_router

setup_logging()

logger = logging.getLogger("backend.startup")


async def _ping_redis() -> None:
    try:
        await redis_client.ping()
        logger.info("Redis connection established url=%s", redact_url(settings.REDIS_URL))
    except Exception:
        logger.warning("Redis ping failed during startup", exc_info=True)


async def _ensure_platform_defaults() -> None:
    async with SessionLocal() as db:
        await PlatformService(db).ensure_defaults()
    logger.info("Platform defaults ensured")


async def _worker_metrics_loop() -> None:
    """Refresh worker gauges independently of health-page traffic."""

    while True:
        try:
            await worker_readiness()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker_metrics_refresh_failed")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Application startup app=%s env=%s log_level=%s",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.LOG_LEVEL.upper(),
    )
    log_eager_mode_startup_warning()
    from backend.modules.manifests import ModuleManifestError, validate_registry
    from backend.modules.platform.profiles import (
        CapabilityProfileError,
        validate_capability_profiles,
    )

    try:
        validate_registry()
        validate_capability_profiles()
    except (ModuleManifestError, CapabilityProfileError):
        logger.exception("Module manifest / capability profile validation failed")
        raise
    validate_rag_config()
    validate_memory_config()
    dependency_started = perf_counter()
    await asyncio.gather(
        object_storage.ensure_bucket(),
        _ping_redis(),
        _ensure_platform_defaults(),
    )
    startup_dependency_duration_seconds.observe(perf_counter() - dependency_started)
    logger.info(
        "Startup dependencies ready duration_ms=%.2f",
        (perf_counter() - dependency_started) * 1000,
    )
    logger.info("Application startup complete")
    worker_metrics_task = asyncio.create_task(_worker_metrics_loop())
    yield
    logger.info("Application shutdown started")
    worker_metrics_task.cancel()
    await asyncio.gather(worker_metrics_task, return_exceptions=True)
    await close_ai_provider_http_clients()
    await close_observability_http_client()
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(DeveloperDiagnosticsMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PublicRateLimitMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Correlation-ID", "X-Request-ID"],
    expose_headers=[
        "X-Correlation-ID",
        "X-Request-ID",
        DIAGNOSTICS_HEADER,
        TRACE_ID_HEADER,
    ],
)

register_exception_handlers(app)
app.include_router(api_router)
app.include_router(health_router)

# Metrics and OTLP instrumentation must register before the ASGI app starts.
setup_observability(app)
