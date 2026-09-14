"""Low-cardinality workflow logging and metrics helpers."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from backend.observability.prometheus_metrics import (
    workflow_duration_seconds,
    workflow_events_total,
)

logger = logging.getLogger("backend.workflow")

P = ParamSpec("P")
R = TypeVar("R")


def observe_async_workflow(
    workflow: str,
    operation: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Instrument an async boundary without recording payloads or identities."""

    def decorator(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            try:
                result = await function(*args, **kwargs)
            except Exception as exc:
                _record(
                    workflow,
                    operation,
                    "failure",
                    started,
                    error_type=type(exc).__name__,
                )
                raise
            _record(workflow, operation, "success", started)
            return result

        return wrapped

    return decorator


def _record(
    workflow: str,
    operation: str,
    outcome: str,
    started: float,
    *,
    error_type: str | None = None,
) -> None:
    duration = max(0.0, time.perf_counter() - started)
    workflow_events_total.labels(workflow, operation, outcome).inc()
    workflow_duration_seconds.labels(workflow, operation).observe(duration)
    extra: dict[str, str] = {
        "event_name": "workflow_completed" if outcome == "success" else "workflow_failed",
        "workflow": workflow,
        "operation": operation,
        "outcome": outcome,
    }
    if error_type:
        extra["error_type"] = error_type
    logger.info("workflow_event", extra=extra)
