from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.db.session import SessionLocal
from backend.observability.instruments import set_current_span_attributes
from backend.observability.prometheus_metrics import (
    worker_job_duration_seconds,
    worker_jobs_total,
)
from backend.workers.async_dispatch import run_async_in_sync_context
from backend.workers.models import ApplicationJob

logger = logging.getLogger("backend.worker")


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"field_names": sorted(payload), "source": "celery"}


async def _create_job(job_type: str, payload: dict[str, Any], correlation_id: str) -> str:
    async with SessionLocal() as db:
        job = ApplicationJob(
            job_type=job_type,
            status="running",
            correlation_id=correlation_id,
            payload=_safe_payload(payload),
            attempts=1,
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.commit()
        return job.id


async def _finish_job(job_id: str, *, status: str, error: str | None = None) -> None:
    async with SessionLocal() as db:
        job = await db.get(ApplicationJob, job_id)
        if job is None:
            return
        job.status = status
        job.last_error = error[:500] if error else None
        job.finished_at = datetime.now(UTC)
        await db.commit()


def run_tracked_sync(
    *,
    job_type: str,
    payload: dict[str, Any],
    runner: Callable[[], None],
    correlation_id: str | None = None,
) -> None:
    started = time.perf_counter()
    job_id = run_async_in_sync_context(
        _create_job(job_type, payload, correlation_id or uuid4().hex)
    )
    set_current_span_attributes(module="workers", job_id=job_id, job_type=job_type)
    try:
        runner()
    except Exception as exc:
        run_async_in_sync_context(_finish_job(job_id, status="failed", error=str(exc)))
        worker_jobs_total.labels(job_type, "failure").inc()
        worker_job_duration_seconds.labels(job_type).observe(time.perf_counter() - started)
        logger.exception(
            "worker_job_failed",
            extra={
                "event_name": "worker_job_failed",
                "job_type": job_type,
                "outcome": "failure",
                "error_type": type(exc).__name__,
            },
        )
        raise
    run_async_in_sync_context(_finish_job(job_id, status="succeeded"))
    worker_jobs_total.labels(job_type, "success").inc()
    worker_job_duration_seconds.labels(job_type).observe(time.perf_counter() - started)
    logger.info(
        "worker_job_completed",
        extra={
            "event_name": "worker_job_completed",
            "job_type": job_type,
            "outcome": "success",
        },
    )
