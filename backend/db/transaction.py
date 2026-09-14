"""Transaction boundary helpers shared by API and worker use cases."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def rollback_safely(db: AsyncSession, *, owner: str) -> None:
    """Rollback a failed use-case transaction without hiding its original error."""
    try:
        await db.rollback()
    except Exception:
        logger.exception("transaction_rollback_failed", extra={"transaction_owner": owner})
