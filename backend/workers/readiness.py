from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import case, func, select

from backend.core.cache import cache_get_or_load_json, redis_client
from backend.core.config import settings
from backend.db.session import SessionLocal
from backend.modules.manifests.celery_contrib import active_celery_queues, queue_name_for_logical
from backend.modules.platform.profiles import resolve_active_modules
from backend.observability import prometheus_metrics
from backend.workers.celery_app import celery_app
from backend.workers.models import ApplicationJob

WORKER_READINESS_CACHE_KEY = "ga:worker:readiness"
# Slightly under the API metrics loop interval so replicas usually share one probe.
WORKER_READINESS_CACHE_TTL_SECONDS = 25


@dataclass(frozen=True, slots=True)
class WorkerReadiness:
    status: str
    detail: str
    queue_depth: int | None = None
    oldest_job_age_seconds: float | None = None
    retry_count: int | None = None
    failed_job_count: int | None = None
    last_successful_heartbeat_at: str | None = None
    queue_depths: dict[str, int] | None = None


def _required_queues() -> tuple[str, ...]:
    """Queues that must be consumed for the active capability profile.

    Always includes the default + email (outbox/identity) queues. Specialist
    queues (memory, ingestion, …) follow active module manifests so a core
    profile does not require inactive workers.
    """

    active = resolve_active_modules().active_modules
    queues = {
        settings.CELERY_TASK_DEFAULT_QUEUE,
        settings.CELERY_EMAIL_QUEUE,
        * (queue_name_for_logical(logical) for logical in active_celery_queues(active)),
    }
    return tuple(sorted(queues))


def _inspect_workers() -> tuple[dict, dict]:
    inspector = celery_app.control.inspect(timeout=0.5)
    return inspector.ping() or {}, inspector.active_queues() or {}


def _publish_gauges(result: WorkerReadiness, *, queues: tuple[str, ...]) -> None:
    if result.oldest_job_age_seconds is not None:
        prometheus_metrics.worker_oldest_job_age_seconds.set(result.oldest_job_age_seconds)
    if result.retry_count is not None:
        prometheus_metrics.worker_retry_count.set(result.retry_count)
    if result.failed_job_count is not None:
        prometheus_metrics.worker_failed_job_count.set(result.failed_job_count)
    depths = result.queue_depths or {}
    for queue in queues:
        if queue in depths:
            prometheus_metrics.worker_queue_depth.labels(queue).set(int(depths[queue]))
    if result.status == "ok" and result.last_successful_heartbeat_at:
        try:
            ts = datetime.fromisoformat(result.last_successful_heartbeat_at).timestamp()
        except ValueError:
            ts = datetime.now(UTC).timestamp()
        prometheus_metrics.worker_heartbeat_timestamp_seconds.labels("celery").set(ts)


def _from_payload(payload: dict) -> WorkerReadiness:
    return WorkerReadiness(
        status=str(payload.get("status") or "error"),
        detail=str(payload.get("detail") or ""),
        queue_depth=payload.get("queue_depth"),
        oldest_job_age_seconds=payload.get("oldest_job_age_seconds"),
        retry_count=payload.get("retry_count"),
        failed_job_count=payload.get("failed_job_count"),
        last_successful_heartbeat_at=payload.get("last_successful_heartbeat_at"),
        queue_depths=payload.get("queue_depths"),
    )


async def _job_metrics(now: datetime) -> tuple[float | None, int | None, int | None]:
    try:
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    select(
                        func.min(ApplicationJob.created_at).filter(
                            ApplicationJob.status.in_(("queued", "running"))
                        ),
                        func.coalesce(
                            func.sum(
                                case(
                                    (ApplicationJob.attempts > 1, ApplicationJob.attempts - 1),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                        func.count(ApplicationJob.id).filter(
                            ApplicationJob.status.in_(("failed", "dead_letter"))
                        ),
                    )
                )
            ).one()
        oldest_created_at, retry_count, failed_count = row
        oldest_age = None
        if oldest_created_at is not None:
            if oldest_created_at.tzinfo is None:
                oldest_created_at = oldest_created_at.replace(tzinfo=UTC)
            oldest_age = max(0.0, (now - oldest_created_at).total_seconds())
        return oldest_age, int(retry_count or 0), int(failed_count or 0)
    except Exception:
        return None, None, None


async def _probe_worker_readiness() -> dict:
    """Expensive probe: DB aggregates + Celery inspect broadcast + Redis LLEN."""

    started = perf_counter()
    outcome = "ok"
    now = datetime.now(UTC)
    queues = _required_queues()

    try:
        oldest_age, retry_count, failed_count = await asyncio.wait_for(
            _job_metrics(now), timeout=1.0
        )
    except TimeoutError:
        oldest_age, retry_count, failed_count = None, None, None

    if settings.CELERY_TASK_ALWAYS_EAGER:
        depths = {queue: 0 for queue in queues}
        result = WorkerReadiness(
            status="ok",
            detail="Celery eager mode is active; no external worker is required",
            queue_depth=0,
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
            last_successful_heartbeat_at=now.isoformat(),
            queue_depths=depths,
        )
        prometheus_metrics.worker_readiness_probe_duration_seconds.labels(outcome).observe(
            perf_counter() - started
        )
        return asdict(result)

    try:
        ping, active_queues = await asyncio.wait_for(
            asyncio.to_thread(_inspect_workers), timeout=2.0
        )
    except Exception:
        outcome = "error"
        result = WorkerReadiness(
            status="error",
            detail="No Celery worker heartbeat received",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
        )
        prometheus_metrics.worker_readiness_probe_duration_seconds.labels(outcome).observe(
            perf_counter() - started
        )
        return asdict(result)

    if not ping:
        outcome = "error"
        result = WorkerReadiness(
            status="error",
            detail="No Celery worker heartbeat received",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
        )
        prometheus_metrics.worker_readiness_probe_duration_seconds.labels(outcome).observe(
            perf_counter() - started
        )
        return asdict(result)

    observed_queues = {
        queue["name"]
        for queues_list in active_queues.values()
        if isinstance(queues_list, list)
        for queue in queues_list
        if isinstance(queue, dict) and queue.get("name")
    }
    missing_queues = sorted(set(queues) - observed_queues)
    if missing_queues:
        outcome = "error"
        result = WorkerReadiness(
            status="error",
            detail=f"Celery workers are not consuming queues: {', '.join(missing_queues)}",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
        )
        prometheus_metrics.worker_readiness_probe_duration_seconds.labels(outcome).observe(
            perf_counter() - started
        )
        return asdict(result)

    try:
        depth_values = await asyncio.gather(*(redis_client.llen(queue) for queue in queues))
    except Exception:
        result = WorkerReadiness(
            status="ok",
            detail="Celery worker heartbeat OK; queue depth unavailable",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
            last_successful_heartbeat_at=now.isoformat(),
        )
        prometheus_metrics.worker_readiness_probe_duration_seconds.labels(outcome).observe(
            perf_counter() - started
        )
        return asdict(result)

    depths = {queue: int(depth) for queue, depth in zip(queues, depth_values, strict=True)}
    result = WorkerReadiness(
        status="ok",
        detail="Celery worker heartbeat and queue bindings OK",
        queue_depth=sum(depths.values()),
        oldest_job_age_seconds=oldest_age,
        retry_count=retry_count,
        failed_job_count=failed_count,
        last_successful_heartbeat_at=now.isoformat(),
        queue_depths=depths,
    )
    prometheus_metrics.worker_readiness_probe_duration_seconds.labels(outcome).observe(
        perf_counter() - started
    )
    return asdict(result)


async def worker_readiness() -> WorkerReadiness:
    """Worker readiness with shared Redis cache for multi-replica API processes.

    Evidence: each probe runs Celery ``control.inspect`` (broadcast), a DB
    aggregate, and per-queue Redis ``LLEN``. Without caching, N API replicas
    repeat that work every ~30s. Coordinated cache keeps one probe hot.
    """

    queues = _required_queues()
    payload = await cache_get_or_load_json(
        WORKER_READINESS_CACHE_KEY,
        ttl_seconds=WORKER_READINESS_CACHE_TTL_SECONDS,
        loader=_probe_worker_readiness,
    )
    if not isinstance(payload, dict):
        result = WorkerReadiness(status="error", detail="Invalid worker readiness cache payload")
        _publish_gauges(result, queues=queues)
        return result
    result = _from_payload(payload)
    _publish_gauges(result, queues=queues)
    return result
