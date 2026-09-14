"""Bounded concurrency for chat provider calls."""

from __future__ import annotations

from contextlib import asynccontextmanager

from backend.core.config import settings
from backend.core.errors import StructuredApiError
from backend.lib.concurrency import LoopLocalLimiter

_chat_provider_limiter = LoopLocalLimiter("chat_provider")


@asynccontextmanager
async def chat_provider_slot():
    timeout = min(
        settings.AI_REQUEST_TIMEOUT_SECONDS,
        settings.CHAT_REQUEST_TIMEOUT_SECONDS,
    )
    try:
        async with _chat_provider_limiter.slot(
            max(1, settings.CHAT_PROVIDER_CONCURRENCY),
            timeout_seconds=timeout,
            kind="chat_provider",
        ):
            yield
    except TimeoutError as exc:
        raise StructuredApiError(
            status_code=503,
            code="provider_busy",
            message="The AI provider is busy. Please try again shortly.",
            retryable=True,
        ) from exc


def get_chat_provider_semaphore():
    """Compatibility accessor for tests and diagnostics."""

    return _chat_provider_limiter.semaphore(max(1, settings.CHAT_PROVIDER_CONCURRENCY))
