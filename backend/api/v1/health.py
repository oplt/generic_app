from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.storage import object_storage
from backend.db.session import engine
from backend.lib.vector_search import pgvector_readiness
from backend.workers.readiness import worker_readiness

health_router = APIRouter(prefix="/health", tags=["health"])


def dependency_operational_state(check_value: str) -> str:
    """Map readiness check values to documented operational states."""
    return {
        "ok": "healthy",
        "error": "unavailable",
        "not_required": "not_required",
        "unknown": "unknown",
    }.get(check_value, check_value)


def _readiness_response(
    checks: dict[str, str],
    *,
    required_checks: set[str] | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    legacy_required = required_checks is None
    required = (
        required_checks
        if required_checks is not None
        else {name for name, value in checks.items() if value not in {"unknown", "not_required"}}
    )
    failed = {name: checks.get(name, "missing") for name in required if checks.get(name) != "ok"}
    response: dict[str, object] = {
        "status": "ok",
        "checks": checks,
        "dependency_states": {
            name: dependency_operational_state(value) for name, value in checks.items()
        },
    }
    if details:
        response["details"] = details
    if not failed:
        return response
    detail: dict[str, object] = {
        "status": "degraded",
        "checks": checks,
        "dependency_states": {
            name: dependency_operational_state(value) for name, value in checks.items()
        },
    }
    if not legacy_required:
        detail["failed_required_checks"] = sorted(failed)
    if details:
        detail["details"] = details
    raise HTTPException(status_code=503, detail=detail)


@health_router.get("/live")
async def live():
    return {"status": "ok"}


@health_router.get("/ready")
async def ready():
    if not settings.HEALTH_READY_PUBLIC and settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    checks: dict[str, str] = {}
    details: dict[str, object] = {}

    try:
        async with engine.connect() as conn:
            from backend.lib.failure_injection import maybe_inject
            from backend.lib.failure_injection.kinds import FaultKind

            maybe_inject(FaultKind.POSTGRES_CONNECTION)
            maybe_inject(FaultKind.POSTGRES_POOL_EXHAUSTED)
            maybe_inject(FaultKind.POSTGRES_SLOW_QUERY)
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "error"

    try:
        from backend.lib.failure_injection import maybe_inject
        from backend.lib.failure_injection.kinds import FaultKind

        maybe_inject(FaultKind.REDIS_UNAVAILABLE)
        maybe_inject(FaultKind.REDIS_TIMEOUT)
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    workers = await worker_readiness()
    checks["queue"] = workers.status
    details["queue"] = workers.detail
    worker_details = {
        "queue_depth": workers.queue_depth,
        "oldest_job_age_seconds": workers.oldest_job_age_seconds,
        "retry_count": workers.retry_count,
        "failed_job_count": workers.failed_job_count,
        "last_successful_heartbeat_at": workers.last_successful_heartbeat_at,
    }
    details["queue_metrics"] = {
        key: value for key, value in worker_details.items() if value is not None
    }

    storage_required = settings.RAG_ENABLED or bool(settings.STORAGE_BUCKET)
    if storage_required:
        storage_ok, storage_detail = await object_storage.readiness()
        checks["storage"] = "ok" if storage_ok else "error"
        details["storage"] = storage_detail
    else:
        checks["storage"] = "not_required"

    vector_required = settings.RAG_ENABLED
    if vector_required and checks["db"] == "ok":
        async with AsyncSession(engine) as db:
            vector = await pgvector_readiness(db)
        checks["vector"] = "ok" if vector.available else "error"
        details["vector"] = vector.reason or "pgvector ready"
    elif vector_required:
        checks["vector"] = "error"
        details["vector"] = "database unavailable"
    else:
        checks["vector"] = "not_required"

    required = {"db", "redis", "queue"}
    if storage_required:
        required.add("storage")
    if vector_required:
        required.add("vector")
    return _readiness_response(checks, required_checks=required, details=details)


@health_router.get("/version")
async def version():
    if not settings.HEALTH_VERSION_PUBLIC and settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "version": settings.APP_VERSION,
        "git_commit": settings.GIT_COMMIT or None,
        "async_jobs": "celery",
    }
