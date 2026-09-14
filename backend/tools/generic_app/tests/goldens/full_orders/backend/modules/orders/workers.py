"""Celery tasks for Orders."""

from __future__ import annotations

import logging

from backend.workers.celery_app import celery_app

logger = logging.getLogger("backend.modules.orders.workers")


@celery_app.task(name="orders.example_task", queue="orders")
def example_orders_task(payload: dict) -> dict:
    """Replace with a real background job; keep queue aligned with the manifest."""

    logger.info("orders_task_received keys=%s", sorted(payload))
    return {"ok": True, "module": "orders"}
