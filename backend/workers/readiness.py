from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.db.session import SessionLocal
from backend.observability import prometheus_metrics
from backend.workers.celery_app import celery_app
from backend.workers.models import ApplicationJob


@dataclass(frozen=True, slots=True)
class WorkerReadiness:
    status: str
    detail: str
    queue_depth: int | None = None
    oldest_job_age_seconds: float | None = None
    retry_count: int | None = None
    failed_job_count: int | None = None
    last_successful_heartbeat_at: str | None = None


def _inspect_workers() -> tuple[dict, dict]:
    inspector = celery_app.control.inspect(timeout=0.5)
    return inspector.ping() or {}, inspector.active_queues() or {}


def _required_queues() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                settings.CELERY_TASK_DEFAULT_QUEUE,
                settings.CELERY_EMAIL_QUEUE,
                settings.CELERY_INGESTION_QUEUE,
                settings.CELERY_CLEANUP_QUEUE,
                settings.CELERY_MEMORY_QUEUE,
                settings.CELERY_EVALUATION_QUEUE,
                settings.CELERY_AI_QUEUE,
            )
        )
    )


async def worker_readiness() -> WorkerReadiness:
    now = datetime.now(UTC)

    async def job_metrics() -> tuple[float | None, int | None, int | None]:
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
                                ApplicationJob.status == "failed"
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

    try:
        oldest_age, retry_count, failed_count = await asyncio.wait_for(job_metrics(), timeout=1.0)
    except TimeoutError:
        oldest_age, retry_count, failed_count = None, None, None
    if oldest_age is not None:
        prometheus_metrics.worker_oldest_job_age_seconds.set(oldest_age)
    if retry_count is not None:
        prometheus_metrics.worker_retry_count.set(retry_count)
    if failed_count is not None:
        prometheus_metrics.worker_failed_job_count.set(failed_count)
    if settings.CELERY_TASK_ALWAYS_EAGER:
        for queue in _required_queues():
            prometheus_metrics.worker_queue_depth.labels(queue).set(0)
        prometheus_metrics.worker_heartbeat_timestamp_seconds.labels("celery").set(
            now.timestamp()
        )
        return WorkerReadiness(
            status="ok",
            detail="Celery eager mode is active; no external worker is required",
            queue_depth=0,
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
            last_successful_heartbeat_at=now.isoformat(),
        )

    try:
        ping, active_queues = await asyncio.wait_for(
            asyncio.to_thread(_inspect_workers), timeout=2.0
        )
    except Exception:
        return WorkerReadiness(
            status="error",
            detail="No Celery worker heartbeat received",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
        )

    if not ping:
        return WorkerReadiness(
            status="error",
            detail="No Celery worker heartbeat received",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
        )

    observed_queues = {
        queue["name"]
        for queues in active_queues.values()
        if isinstance(queues, list)
        for queue in queues
        if isinstance(queue, dict) and queue.get("name")
    }
    missing_queues = sorted(set(_required_queues()) - observed_queues)
    if missing_queues:
        return WorkerReadiness(
            status="error",
            detail=f"Celery workers are not consuming queues: {', '.join(missing_queues)}",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
        )

    try:
        depths = await asyncio.gather(
            *(redis_client.llen(queue) for queue in _required_queues())
        )
    except Exception:
        prometheus_metrics.worker_heartbeat_timestamp_seconds.labels("celery").set(
            now.timestamp()
        )
        return WorkerReadiness(
            status="ok",
            detail="Celery worker heartbeat OK; queue depth unavailable",
            oldest_job_age_seconds=oldest_age,
            retry_count=retry_count,
            failed_job_count=failed_count,
            last_successful_heartbeat_at=now.isoformat(),
        )
    for queue, depth in zip(_required_queues(), depths, strict=True):
        prometheus_metrics.worker_queue_depth.labels(queue).set(int(depth))
    prometheus_metrics.worker_heartbeat_timestamp_seconds.labels("celery").set(
        now.timestamp()
    )
    return WorkerReadiness(
        status="ok",
        detail="Celery worker heartbeat and queue bindings OK",
        queue_depth=sum(int(depth) for depth in depths),
        oldest_job_age_seconds=oldest_age,
        retry_count=retry_count,
        failed_job_count=failed_count,
        last_successful_heartbeat_at=now.isoformat(),
    )
