from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.transaction import rollback_safely
from backend.modules.rag.infrastructure.models import RagIngestionJob
from backend.workers.models import BackgroundJobOutbox

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    """Detached publish data for one committed outbox lease."""

    outbox_id: str
    job_id: str
    job_type: str
    payload: dict
    attempts: int
    lease_token: str


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


async def _dead_letter(
    db: AsyncSession,
    row: BackgroundJobOutbox,
    *,
    reason: str,
    now: datetime,
) -> None:
    row.status = "dead_letter"
    row.last_error = reason
    row.locked_at = None
    row.lease_token = None
    row.dispatched_at = None
    job = await db.scalar(select(RagIngestionJob).where(RagIngestionJob.id == row.job_id))
    if job and job.status != "completed":
        job.status = "failed"
        job.error_message = reason
        job.finished_at = now
        job.heartbeat_at = now


async def _claim_pending_job_events(
    db: AsyncSession,
    *,
    batch_size: int,
) -> list[OutboxClaim]:
    """Claim rows and commit before any broker call is made."""

    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.OUTBOX_DISPATCH_LEASE_SECONDS)
    result = await db.execute(
        select(BackgroundJobOutbox)
        .where(
            or_(
                and_(
                    BackgroundJobOutbox.status == "pending",
                    BackgroundJobOutbox.available_at <= now,
                ),
                and_(
                    BackgroundJobOutbox.status == "dispatching",
                    or_(
                        BackgroundJobOutbox.locked_at.is_(None),
                        BackgroundJobOutbox.locked_at <= stale_before,
                    ),
                ),
            )
        )
        .with_for_update(skip_locked=True)
        .order_by(BackgroundJobOutbox.created_at)
        .limit(batch_size)
    )
    rows = list(result.scalars().all())
    if not rows:
        return []
    claims: list[OutboxClaim] = []
    try:
        for row in rows:
            row.status = "dispatching"
            row.attempts += 1
            row.locked_at = now
            lease_token = uuid4().hex
            row.lease_token = lease_token
            if row.deadline_at and row.deadline_at <= now:
                await _dead_letter(db, row, reason="Outbox delivery deadline exceeded", now=now)
                continue
            if row.attempts > settings.RAG_INGESTION_MAX_ATTEMPTS:
                await _dead_letter(
                    db,
                    row,
                    reason="Outbox delivery exceeded the maximum retry count",
                    now=now,
                )
                continue
            claims.append(
                OutboxClaim(
                    outbox_id=row.id,
                    job_id=row.job_id,
                    job_type=row.job_type,
                    payload=dict(row.payload or {}),
                    attempts=row.attempts,
                    lease_token=lease_token,
                )
            )
        await db.flush()
        await db.commit()
        return claims
    except Exception:
        await rollback_safely(db, owner="worker.outbox.claim")
        raise


async def _ack_claim(
    db: AsyncSession,
    claim: OutboxClaim,
    *,
    dispatched: bool,
    now: datetime,
    error: str | None = None,
) -> bool:
    """Persist one publish result only if this dispatcher still owns the lease."""

    values = {
        "status": "dispatched" if dispatched else "pending",
        "locked_at": None,
        "lease_token": None,
        "last_error": None if dispatched else (error or "Outbox delivery failed")[:500],
    }
    if dispatched:
        values.update(dispatched_at=now)
    else:
        values.update(
            available_at=now
            + timedelta(seconds=min(60 * claim.attempts, 900)),
            dispatched_at=None,
        )
    try:
        result = await db.execute(
            update(BackgroundJobOutbox)
            .where(
                BackgroundJobOutbox.id == claim.outbox_id,
                BackgroundJobOutbox.status == "dispatching",
                BackgroundJobOutbox.lease_token == claim.lease_token,
            )
            .values(**values)
        )
        await db.commit()
        return result.rowcount == 1
    except Exception:
        await rollback_safely(db, owner="worker.outbox.ack")
        raise


async def dispatch_pending_job_events(db: AsyncSession, *, batch_size: int = 50) -> int:
    claims = await _claim_pending_job_events(db, batch_size=batch_size)
    if not claims:
        return 0

    from backend.workers.tasks import enqueue_outbox_job

    dispatched = 0
    for claim in claims:
        now = datetime.now(UTC)
        try:
            # The claim transaction is committed before this network call. A
            # crash after broker acceptance leaves the lease for stale recovery;
            # the stable job_id makes the consumer duplicate-safe.
            enqueue_outbox_job.apply_async(
                kwargs={"job_type": claim.job_type, **claim.payload},
                queue=settings.CELERY_TASK_DEFAULT_QUEUE,
            )
        except Exception as exc:
            await _ack_claim(db, claim, dispatched=False, now=now, error=str(exc))
            logger.warning("Outbox dispatch failed job=%s", claim.job_id, exc_info=True)
            continue
        if await _ack_claim(db, claim, dispatched=True, now=now):
            dispatched += 1
    return dispatched
