"""Durable claim/complete ledger for externally visible Celery effects."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.core.config import settings
from backend.db.session import SessionLocal
from backend.db.transaction import rollback_safely
from backend.workers.models import ExternalEffect

logger = logging.getLogger(__name__)

EFFECT_EMAIL = "email"
STATUS_IN_FLIGHT = "in_flight"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"


class ExternalEffectInFlightError(Exception):
    """Another delivery still owns this effect; retry after the lease window."""


@dataclass(frozen=True, slots=True)
class EffectClaim:
    """Result of claiming one external effect operation."""

    should_execute: bool
    effect_id: str | None
    status: str
    attempts: int
    provider_idempotency_key: str


def hash_effect_payload(*parts: str | None) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update((part or "").encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def provider_key_for_operation(operation_id: str) -> str:
    digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
    return f"<{digest}@generic-app.invalid>"


def _is_stale(effect: ExternalEffect, *, now: datetime) -> bool:
    started = effect.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    lease = timedelta(seconds=settings.EXTERNAL_EFFECT_LEASE_SECONDS)
    return started <= now - lease


async def begin_external_effect(
    *,
    operation_id: str,
    effect_type: str,
    payload_hash: str,
    provider_idempotency_key: str | None = None,
) -> EffectClaim:
    """Claim an effect or skip when a prior delivery already owns the outcome.

    Status policy:
    - ``succeeded`` → skip (one visible effect already recorded)
    - fresh ``in_flight`` → skip for the caller to defer (concurrent/crash gap)
    - stale ``in_flight`` / ``failed`` / missing → claim and proceed
    """

    key = provider_idempotency_key or provider_key_for_operation(operation_id)
    now = datetime.now(UTC)

    for insert_attempt in range(2):
        async with SessionLocal() as db:
            try:
                existing = await db.scalar(
                    select(ExternalEffect)
                    .where(
                        ExternalEffect.operation_id == operation_id,
                        ExternalEffect.effect_type == effect_type,
                    )
                    .with_for_update()
                )
                if existing is not None:
                    if existing.payload_hash != payload_hash:
                        raise ValueError(
                            "External effect payload does not match prior operation_id claim"
                        )
                    if existing.status == STATUS_SUCCEEDED:
                        return EffectClaim(
                            should_execute=False,
                            effect_id=existing.id,
                            status=existing.status,
                            attempts=existing.attempts,
                            provider_idempotency_key=existing.provider_idempotency_key
                            or key,
                        )
                    if existing.status == STATUS_IN_FLIGHT and not _is_stale(
                        existing, now=now
                    ):
                        return EffectClaim(
                            should_execute=False,
                            effect_id=existing.id,
                            status=existing.status,
                            attempts=existing.attempts,
                            provider_idempotency_key=existing.provider_idempotency_key
                            or key,
                        )
                    existing.status = STATUS_IN_FLIGHT
                    existing.attempts = (existing.attempts or 0) + 1
                    existing.provider_idempotency_key = (
                        existing.provider_idempotency_key or key
                    )
                    existing.last_error = None
                    existing.started_at = now
                    existing.completed_at = None
                    existing.updated_at = now
                    await db.commit()
                    return EffectClaim(
                        should_execute=True,
                        effect_id=existing.id,
                        status=existing.status,
                        attempts=existing.attempts,
                        provider_idempotency_key=existing.provider_idempotency_key,
                    )

                effect = ExternalEffect(
                    id=str(uuid4()),
                    operation_id=operation_id,
                    effect_type=effect_type,
                    status=STATUS_IN_FLIGHT,
                    payload_hash=payload_hash,
                    attempts=1,
                    provider_idempotency_key=key,
                    started_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(effect)
                await db.commit()
                return EffectClaim(
                    should_execute=True,
                    effect_id=effect.id,
                    status=effect.status,
                    attempts=effect.attempts,
                    provider_idempotency_key=key,
                )
            except IntegrityError:
                await rollback_safely(db, owner="worker.effect.begin")
                if insert_attempt:
                    raise
            except Exception:
                await rollback_safely(db, owner="worker.effect.begin")
                raise

    raise RuntimeError("Unable to claim external effect")


async def complete_external_effect(
    *,
    operation_id: str,
    effect_type: str,
    status: str,
    error: str | None = None,
) -> None:
    if status not in {STATUS_SUCCEEDED, STATUS_FAILED}:
        raise ValueError(f"Unsupported external effect status: {status}")
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        try:
            effect = await db.scalar(
                select(ExternalEffect)
                .where(
                    ExternalEffect.operation_id == operation_id,
                    ExternalEffect.effect_type == effect_type,
                )
                .with_for_update()
            )
            if effect is None:
                logger.warning(
                    "external_effect_missing",
                    extra={
                        "event_name": "external_effect_missing",
                        "operation_id": operation_id,
                        "effect_type": effect_type,
                    },
                )
                return
            if effect.status == STATUS_SUCCEEDED:
                return
            effect.status = status
            effect.last_error = error[:500] if error else None
            effect.completed_at = now
            effect.updated_at = now
            await db.commit()
        except Exception:
            await rollback_safely(db, owner="worker.effect.complete")
            raise
