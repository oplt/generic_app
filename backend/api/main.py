import asyncio
import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.middleware.correlation_id import CorrelationIdMiddleware
from backend.api.middleware.csrf import CSRFMiddleware
from backend.api.middleware.public_rate_limit import PublicRateLimitMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.api.middleware.security_headers import SecurityHeadersMiddleware
from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.error_handler import register_exception_handlers
from backend.core.log_redaction import redact_url
from backend.core.logging import setup_logging
from backend.core.storage import object_storage
from backend.db.session import SessionLocal, engine
from backend.modules.ai.providers import close_ai_provider_http_clients
from backend.modules.developer_diagnostics.middleware import DeveloperDiagnosticsMiddleware
from backend.modules.memory.infrastructure.memory_config import validate_memory_config
from backend.modules.platform.service import PlatformService
from backend.modules.rag.infrastructure.rag_config import validate_rag_config
from backend.observability import setup_observability
from backend.observability.prometheus_metrics import startup_dependency_duration_seconds
from backend.observability.request_diagnostics import (
    DIAGNOSTICS_HEADER,
    TRACE_ID_HEADER,
)
from backend.observability.service import close_observability_http_client
from backend.workers.async_dispatch import log_eager_mode_startup_warning
from backend.workers.readiness import worker_readiness

from .router import api_router
from .v1.health import health_router

setup_logging()

logger = logging.getLogger("backend.startup")


async def _ping_redis() -> None:
    """Soft dependency: cache/rate-limit/broker helpers degrade without Redis."""

    try:
        await redis_client.ping()
        logger.info("Redis connection established url=%s", redact_url(settings.REDIS_URL))
    except Exception:
        logger.warning("Redis ping failed during startup (soft)", exc_info=True)


async def _ensure_platform_defaults() -> None:
    """Hard dependency: Postgres must accept platform seed writes."""

    async with SessionLocal() as db:
        await PlatformService(db).ensure_defaults()
    logger.info("Platform defaults ensured")


async def _bootstrap_object_storage(*, required: bool) -> None:
    """Capability-scoped bucket prep.

    Soft when storage is not a readiness requirement (core/lean avatars optional).
    Soft-fail even when required — `/health/ready` gates traffic; startup logs error.
    """

    if not object_storage.is_configured:
        if required:
            logger.error(
                "Object storage required by active capabilities but STORAGE_BUCKET unset"
            )
        else:
            logger.info("Object storage bootstrap skipped (not configured; not required)")
        return
    if not settings.STORAGE_AUTO_CREATE_BUCKET:
        logger.info(
            "Object storage configured; auto-create disabled required=%s",
            required,
        )
        return
    await object_storage.ensure_bucket()
    if object_storage._last_bootstrap_error and required:
        logger.error(
            "Object storage bootstrap failed while required by active capabilities "
            "error=%s",
            object_storage._last_bootstrap_error,
        )


async def _worker_metrics_loop() -> None:
    """Refresh worker gauges independently of health-page traffic.

    ``worker_readiness`` uses a shared Redis cache so multiple API replicas do
    not each broadcast Celery inspect / DB aggregates every interval.
    """

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
        resolve_active_modules,
        validate_capability_profiles,
    )

    try:
        validate_registry()
        validate_capability_profiles()
    except (ModuleManifestError, CapabilityProfileError):
        logger.exception("Module manifest / capability profile validation failed")
        raise

    resolution = resolve_active_modules()
    active = set(resolution.active_modules)
    storage_required = "storage" in resolution.health_checks
    if "rag" in active:
        validate_rag_config()
    if "memory" in active:
        validate_memory_config()
    logger.info(
        "Capability profile active profile=%s modules=%s health_checks=%s",
        settings.capability_profile,
        ",".join(sorted(active)),
        ",".join(resolution.health_checks),
    )
    dependency_started = perf_counter()
    # Soft deps first (never abort gather); hard platform seed last so DB
    # failures still fail startup intentionally.
    await asyncio.gather(
        _bootstrap_object_storage(required=storage_required),
        _ping_redis(),
    )
    await _ensure_platform_defaults()
    startup_dependency_duration_seconds.observe(perf_counter() - dependency_started)
    logger.info(
        "Startup dependencies ready duration_ms=%.2f storage_required=%s",
        (perf_counter() - dependency_started) * 1000,
        storage_required,
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


def create_app(*, include_lifespan: bool = True) -> FastAPI:
    """Build the FastAPI application.

    Layers (keep separate for tooling):
    * configuration parsing → ``backend.core.config.settings``
    * app construction → routers/middleware/OpenAPI (this function)
    * runtime lifespan → DB seed, Redis ping, storage bootstrap, metrics loop

    OpenAPI export uses ``include_lifespan=False`` so schema generation never
    runs startup dependency checks (Postgres / Redis / MinIO / providers).
    """

    application = FastAPI(
        title=settings.APP_NAME,
        docs_url="/docs" if settings.APP_ENV != "production" else None,
        redoc_url="/redoc" if settings.APP_ENV != "production" else None,
        lifespan=lifespan if include_lifespan else None,
    )

    application.add_middleware(DeveloperDiagnosticsMiddleware)
    application.add_middleware(CorrelationIdMiddleware)
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(PublicRateLimitMiddleware)
    application.add_middleware(CSRFMiddleware)
    application.add_middleware(
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

    register_exception_handlers(application)
    application.include_router(api_router)
    application.include_router(health_router)

    # Metrics and OTLP instrumentation must register before the ASGI app starts.
    setup_observability(application)
    return application


app = create_app()
