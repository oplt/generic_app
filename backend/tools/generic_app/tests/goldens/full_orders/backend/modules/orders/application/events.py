"""Outbox-friendly event helpers for Orders (no side effects until wired)."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orders.infrastructure.models import Order

logger = logging.getLogger("backend.modules.orders.events")


async def emit_order_created(db: AsyncSession, item: Order) -> None:
    """Hook for outbox / domain events. Replace with OutboxService when ready."""

    _ = db
    logger.info(
        "orders_created id=%s user_id=%s",
        item.id,
        item.user_id,
    )
