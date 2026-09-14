from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.workers.models import BackgroundJobOutbox

logger = logging.getLogger(__name__)


async def enqueue_job_event(
    db: AsyncSession,
    *,
    job_id: str,
    job_type: str,
    payload: dict,
) -> None:
    # Local eager mode uses the explicitly supported in-process dev path. Do not
    # leave a second durable event that would replay the same job later.
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return
    from backend.modules.rag.infrastructure.models import RagIngestionJob

    existing = await db.scalar(
        select(BackgroundJobOutbox).where(BackgroundJobOutbox.job_id == job_id)
    )
    if existing:
        return
    deadline_at = await db.scalar(
        select(RagIngestionJob.deadline_at).where(RagIngestionJob.id == job_id)
    )
    db.add(
        BackgroundJobOutbox(
            job_id=job_id,
            job_type=job_type,
            payload=payload,
            deadline_at=deadline_at,
        )
    )


async def dispatch_pending_job_events(db: AsyncSession, *, batch_size: int = 50) -> int:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=10)
    rows = list(
        (
            await db.execute(
                select(BackgroundJobOutbox)
                .where(
                    or_(
                        and_(
                            BackgroundJobOutbox.status == "pending",
                            BackgroundJobOutbox.available_at <= now,
                        ),
                        and_(
                            BackgroundJobOutbox.status == "dispatching",
                            BackgroundJobOutbox.locked_at <= stale_before,
                        ),
                    )
                )
                .with_for_update(skip_locked=True)
                .order_by(BackgroundJobOutbox.created_at)
                .limit(batch_size)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0

    from backend.modules.rag.infrastructure.models import RagIngestionJob
    from backend.workers.tasks import enqueue_outbox_job

    async def dead_letter(row: BackgroundJobOutbox, reason: str) -> None:
        row.status = "dead_letter"
        row.last_error = reason
        job = await db.scalar(
            select(RagIngestionJob).where(RagIngestionJob.id == row.job_id)
        )
        if job and job.status != "completed":
            job.status = "failed"
            job.error_message = reason
            job.finished_at = now
            job.heartbeat_at = now

    dispatched = 0
    for row in rows:
        row.status = "dispatching"
        row.attempts += 1
        row.locked_at = now
        await db.flush()
        if row.deadline_at and row.deadline_at <= now:
            await dead_letter(row, "Outbox delivery deadline exceeded")
            continue
        if row.attempts > settings.RAG_INGESTION_MAX_ATTEMPTS:
            await dead_letter(row, "Outbox delivery exceeded the maximum retry count")
            continue
        try:
            enqueue_outbox_job.apply_async(
                kwargs={"job_type": row.job_type, **row.payload},
                queue=settings.CELERY_TASK_DEFAULT_QUEUE,
            )
        except Exception as exc:
            row.status = "pending"
            row.last_error = str(exc)[:500]
            row.available_at = now + timedelta(seconds=min(60 * row.attempts, 900))
            logger.warning("Outbox dispatch failed job=%s", row.job_id, exc_info=True)
            continue
        row.status = "dispatched"
        row.dispatched_at = now
        dispatched += 1
    await db.commit()
    return dispatched
