from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.core.config import settings
from backend.db.session import SessionLocal
from backend.db.transaction import rollback_safely
from backend.observability.instruments import set_current_span_attributes
from backend.observability.prometheus_metrics import (
    worker_job_duration_seconds,
    worker_job_queue_latency_seconds,
    worker_job_retries_total,
    worker_jobs_total,
)
from backend.workers.async_dispatch import run_async_in_sync_context
from backend.workers.effect_ledger import ExternalEffectInFlightError
from backend.workers.models import ApplicationJob

logger = logging.getLogger("backend.worker")

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_DEAD_LETTER = "dead_letter"


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"field_names": sorted(payload), "source": "celery"}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _classify_error(exc: BaseException) -> str:
    name = type(exc).__name__
    message = str(exc).strip().replace("\n", " ")
    if len(message) > 180:
        message = f"{message[:177]}..."
    return f"{name}: {message}" if message else name


@dataclass(frozen=True, slots=True)
class ClaimResult:
    job_id: str
    should_run: bool
    outcome: str
    attempt: int
    queue_latency_seconds: float | None = None


def _is_stale_running(job: ApplicationJob, *, now: datetime) -> bool:
    started = _aware(job.started_at) or _aware(job.updated_at) or _aware(job.created_at)
    if started is None:
        return True
    lease = timedelta(seconds=settings.WORKER_JOB_RUNNING_LEASE_SECONDS)
    return started <= now - lease


def _deadline_expired(job: ApplicationJob, *, now: datetime) -> bool:
    deadline = _aware(job.deadline_at)
    return deadline is not None and deadline <= now


async def ensure_queued_job(
    *,
    job_type: str,
    payload: dict[str, Any],
    correlation_id: str,
    operation_id: str | None = None,
    max_attempts: int = 3,
    retryable: bool = True,
    deadline_at: datetime | None = None,
) -> str:
    """Create one logical job in ``queued`` state (idempotent on ``operation_id``)."""

    now = datetime.now(UTC)
    for insert_attempt in range(2):
        async with SessionLocal() as db:
            try:
                if operation_id:
                    existing = await db.scalar(
                        select(ApplicationJob)
                        .where(ApplicationJob.operation_id == operation_id)
                        .with_for_update()
                    )
                    if existing is not None:
                        return existing.id

                job = ApplicationJob(
                    job_type=job_type,
                    status=STATUS_QUEUED,
                    correlation_id=correlation_id,
                    operation_id=operation_id,
                    payload=_safe_payload(payload),
                    attempts=0,
                    max_attempts=max_attempts,
                    retryable=retryable,
                    available_at=now,
                    deadline_at=deadline_at,
                )
                db.add(job)
                await db.commit()
                return job.id
            except IntegrityError:
                await rollback_safely(db, owner="worker.job.enqueue")
                if not operation_id or insert_attempt:
                    raise
            except Exception:
                await rollback_safely(db, owner="worker.job.enqueue")
                raise
    raise RuntimeError("Unable to enqueue worker job")


async def _claim_job(
    job_type: str,
    payload: dict[str, Any],
    correlation_id: str,
    operation_id: str | None,
    max_attempts: int,
    retryable: bool,
    deadline_at: datetime | None,
) -> ClaimResult:
    """Upsert/lock one logical job and transition it to ``running`` when executable."""

    now = datetime.now(UTC)
    for insert_attempt in range(2):
        async with SessionLocal() as db:
            try:
                existing = None
                if operation_id:
                    existing = await db.scalar(
                        select(ApplicationJob)
                        .where(ApplicationJob.operation_id == operation_id)
                        .with_for_update()
                    )

                if existing is None:
                    job = ApplicationJob(
                        job_type=job_type,
                        status=STATUS_RUNNING,
                        correlation_id=correlation_id,
                        operation_id=operation_id,
                        payload=_safe_payload(payload),
                        attempts=1,
                        max_attempts=max_attempts,
                        retryable=retryable,
                        available_at=now,
                        deadline_at=deadline_at,
                        started_at=now,
                    )
                    db.add(job)
                    await db.commit()
                    return ClaimResult(
                        job_id=job.id,
                        should_run=True,
                        outcome="run",
                        attempt=1,
                        queue_latency_seconds=0.0,
                    )

                if existing.status == STATUS_SUCCEEDED:
                    return ClaimResult(
                        job_id=existing.id,
                        should_run=False,
                        outcome="deduplicated",
                        attempt=existing.attempts or 0,
                    )

                if existing.status == STATUS_DEAD_LETTER:
                    return ClaimResult(
                        job_id=existing.id,
                        should_run=False,
                        outcome="dead_letter",
                        attempt=existing.attempts or 0,
                    )

                if existing.status == STATUS_RUNNING and not _is_stale_running(
                    existing, now=now
                ):
                    return ClaimResult(
                        job_id=existing.id,
                        should_run=False,
                        outcome="in_flight",
                        attempt=existing.attempts or 0,
                    )

                if _deadline_expired(existing, now=now):
                    existing.status = STATUS_DEAD_LETTER
                    existing.last_error = "deadline_exceeded"
                    existing.finished_at = now
                    await db.commit()
                    return ClaimResult(
                        job_id=existing.id,
                        should_run=False,
                        outcome="expired",
                        attempt=existing.attempts or 0,
                    )

                next_attempt = (existing.attempts or 0) + 1
                existing.max_attempts = max_attempts or existing.max_attempts
                existing.retryable = retryable
                if deadline_at is not None:
                    existing.deadline_at = deadline_at

                if next_attempt > (existing.max_attempts or max_attempts):
                    existing.status = STATUS_DEAD_LETTER
                    existing.attempts = next_attempt
                    existing.last_error = existing.last_error or "max_attempts_exceeded"
                    existing.finished_at = now
                    await db.commit()
                    return ClaimResult(
                        job_id=existing.id,
                        should_run=False,
                        outcome="dead_letter",
                        attempt=next_attempt,
                    )

                available_at = _aware(existing.available_at) or _aware(existing.created_at) or now
                existing.status = STATUS_RUNNING
                existing.attempts = next_attempt
                existing.started_at = now
                existing.finished_at = None
                existing.last_error = None
                await db.commit()
                return ClaimResult(
                    job_id=existing.id,
                    should_run=True,
                    outcome="run",
                    attempt=next_attempt,
                    queue_latency_seconds=max(0.0, (now - available_at).total_seconds()),
                )
            except IntegrityError:
                await rollback_safely(db, owner="worker.job.claim")
                if not operation_id or insert_attempt:
                    raise
            except Exception:
                await rollback_safely(db, owner="worker.job.claim")
                raise

    raise RuntimeError("Unable to claim worker job")


async def _finish_job(
    job_id: str,
    *,
    status: str,
    error: str | None = None,
) -> None:
    async with SessionLocal() as db:
        try:
            job = await db.get(ApplicationJob, job_id)
            if job is None:
                return
            if job.status in {STATUS_SUCCEEDED, STATUS_DEAD_LETTER}:
                return
            now = datetime.now(UTC)
            terminal = status
            if status == STATUS_FAILED and (
                not job.retryable
                or (job.attempts or 0) >= (job.max_attempts or 1)
            ):
                terminal = STATUS_DEAD_LETTER
            job.status = terminal
            job.last_error = error[:500] if error else None
            job.finished_at = now
            await db.commit()
        except Exception:
            await rollback_safely(db, owner="worker.job.finish")
            raise


async def _release_job_for_retry(job_id: str, *, delay_seconds: int, error: str) -> None:
    """Return a claimed job to ``queued`` so Celery can retry without losing history."""

    async with SessionLocal() as db:
        try:
            job = await db.get(ApplicationJob, job_id)
            if job is None or job.status != STATUS_RUNNING:
                return
            now = datetime.now(UTC)
            job.status = STATUS_QUEUED
            job.available_at = now + timedelta(seconds=max(0, delay_seconds))
            job.started_at = None
            job.finished_at = None
            job.last_error = error[:500]
            await db.commit()
        except Exception:
            await rollback_safely(db, owner="worker.job.release")
            raise


def run_tracked_sync(
    *,
    job_type: str,
    payload: dict[str, Any],
    runner: Callable[[], None],
    correlation_id: str | None = None,
    operation_id: str | None = None,
    max_attempts: int | None = None,
    retryable: bool = True,
    deadline_at: datetime | None = None,
) -> None:
    started = time.perf_counter()
    attempts_limit = max_attempts or settings.WORKER_JOB_DEFAULT_MAX_ATTEMPTS
    claim = run_async_in_sync_context(
        _claim_job(
            job_type,
            payload,
            correlation_id or uuid4().hex,
            operation_id,
            attempts_limit,
            retryable,
            deadline_at,
        )
    )
    set_current_span_attributes(
        module="workers",
        job_id=claim.job_id,
        job_type=job_type,
        attempt=claim.attempt,
        operation_id=operation_id or "",
    )

    if claim.attempt > 1 and claim.should_run:
        worker_job_retries_total.labels(job_type).inc()

    if not claim.should_run:
        worker_jobs_total.labels(job_type, claim.outcome).inc()
        worker_job_duration_seconds.labels(job_type).observe(time.perf_counter() - started)
        logger.info(
            "worker_job_skipped",
            extra={
                "event_name": "worker_job_skipped",
                "job_type": job_type,
                "outcome": claim.outcome,
                "attempt": claim.attempt,
                "operation_id": operation_id,
            },
        )
        return

    if claim.queue_latency_seconds is not None:
        worker_job_queue_latency_seconds.labels(job_type).observe(claim.queue_latency_seconds)

    try:
        runner()
    except ExternalEffectInFlightError as exc:
        run_async_in_sync_context(
            _release_job_for_retry(
                claim.job_id,
                delay_seconds=settings.EXTERNAL_EFFECT_LEASE_SECONDS,
                error=_classify_error(exc),
            )
        )
        worker_jobs_total.labels(job_type, "deferred").inc()
        worker_job_duration_seconds.labels(job_type).observe(time.perf_counter() - started)
        logger.info(
            "worker_job_deferred",
            extra={
                "event_name": "worker_job_deferred",
                "job_type": job_type,
                "outcome": "deferred",
                "attempt": claim.attempt,
                "operation_id": operation_id,
            },
        )
        raise
    except Exception as exc:
        run_async_in_sync_context(
            _finish_job(claim.job_id, status=STATUS_FAILED, error=_classify_error(exc))
        )
        worker_jobs_total.labels(job_type, "failure").inc()
        worker_job_duration_seconds.labels(job_type).observe(time.perf_counter() - started)
        logger.exception(
            "worker_job_failed",
            extra={
                "event_name": "worker_job_failed",
                "job_type": job_type,
                "outcome": "failure",
                "attempt": claim.attempt,
                "error_type": type(exc).__name__,
                "operation_id": operation_id,
            },
        )
        raise

    run_async_in_sync_context(_finish_job(claim.job_id, status=STATUS_SUCCEEDED))
    worker_jobs_total.labels(job_type, "success").inc()
    worker_job_duration_seconds.labels(job_type).observe(time.perf_counter() - started)
    logger.info(
        "worker_job_completed",
        extra={
            "event_name": "worker_job_completed",
            "job_type": job_type,
            "outcome": "success",
            "attempt": claim.attempt,
            "queue_latency_seconds": claim.queue_latency_seconds,
            "operation_id": operation_id,
        },
    )
