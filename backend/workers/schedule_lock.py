"""Distributed singleton locks for Celery beat schedules.

Beat can enqueue overlapping ticks when the prior run is slow or when multiple
beat processes race. Redis NX locks reduce duplicate starts; chat retention also
takes a PostgreSQL transaction-scoped advisory lock so deletes remain exclusive
even when Redis is unavailable.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Literal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.observability.prometheus_metrics import worker_beat_schedule_lock_total

logger = logging.getLogger(__name__)

BeatScheduleName = Literal["outbox-dispatch", "chat-retention"]

# Stable int pair for pg_try_advisory_xact_lock (generic_app chat retention).
CHAT_RETENTION_ADVISORY_KEY1 = 0x47415254  # 'GART'
CHAT_RETENTION_ADVISORY_KEY2 = 0x43485254  # 'CHRT'

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def beat_lock_redis_key(name: BeatScheduleName) -> str:
    return f"ga:beat:lock:{name}"


def _ttl_seconds(name: BeatScheduleName) -> int:
    if name == "outbox-dispatch":
        return settings.WORKER_BEAT_OUTBOX_LOCK_TTL_SECONDS
    return settings.WORKER_BEAT_CHAT_RETENTION_LOCK_TTL_SECONDS


async def try_acquire_beat_lock(
    name: BeatScheduleName,
    *,
    on_redis_error: Literal["proceed", "skip"] = "proceed",
) -> str | None:
    """Acquire a Redis NX lock for a beat schedule.

    Returns a release token when acquired, or None when another holder owns the
    lock (or when Redis errors and ``on_redis_error='skip'``).

    ``on_redis_error='proceed'`` fail-opens so outbox / retention can rely on
    SKIP LOCKED or the Postgres advisory lock instead of stalling forever.
    """
    key = beat_lock_redis_key(name)
    token = uuid4().hex
    try:
        acquired = await redis_client.set(key, token, nx=True, ex=_ttl_seconds(name))
    except Exception:
        logger.warning("beat schedule redis lock unavailable schedule=%s", name, exc_info=True)
        worker_beat_schedule_lock_total.labels(
            schedule=name, backend="redis", outcome="redis_error"
        ).inc()
        if on_redis_error == "proceed":
            return f"redis-unavailable:{token}"
        return None
    if acquired:
        worker_beat_schedule_lock_total.labels(
            schedule=name, backend="redis", outcome="acquired"
        ).inc()
        return token
    worker_beat_schedule_lock_total.labels(
        schedule=name, backend="redis", outcome="skipped"
    ).inc()
    logger.info("beat schedule lock held; skipping overlapping run schedule=%s", name)
    return None


async def release_beat_lock(name: BeatScheduleName, token: str | None) -> None:
    if not token or token.startswith("redis-unavailable:"):
        return
    with suppress(Exception):
        await redis_client.eval(_RELEASE_LOCK_SCRIPT, 1, beat_lock_redis_key(name), token)


async def try_acquire_chat_retention_advisory_lock(db: AsyncSession) -> bool:
    """Transaction-scoped Postgres lock; released on commit/rollback."""
    result = await db.execute(
        text("SELECT pg_try_advisory_xact_lock(:k1, :k2)"),
        {
            "k1": CHAT_RETENTION_ADVISORY_KEY1,
            "k2": CHAT_RETENTION_ADVISORY_KEY2,
        },
    )
    acquired = bool(result.scalar())
    worker_beat_schedule_lock_total.labels(
        schedule="chat-retention",
        backend="postgres",
        outcome="acquired" if acquired else "skipped",
    ).inc()
    if not acquired:
        logger.info("chat retention advisory lock held; skipping overlapping delete")
    return acquired
