"""Per-user and process-wide limits for external web search."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.core.config import settings
from backend.core.rate_limit import check_rate_limit
from backend.lib.concurrency import LoopLocalLimiter
from backend.modules.chat.application.search import SearchProviderError

_web_search_limiter = LoopLocalLimiter("web_search")


async def enforce_web_search_limits(user_id: str) -> None:
    """Apply per-user rolling and optional daily search budgets."""

    if settings.WEB_SEARCH_RATE_LIMIT_REQUESTS > 0:
        await check_rate_limit(
            f"rate_limit:web_search:{user_id}",
            settings.WEB_SEARCH_RATE_LIMIT_REQUESTS,
            settings.WEB_SEARCH_RATE_LIMIT_WINDOW_SECONDS,
        )
    if settings.WEB_SEARCH_DAILY_REQUESTS > 0:
        await check_rate_limit(
            f"rate_limit:web_search:daily:{user_id}",
            settings.WEB_SEARCH_DAILY_REQUESTS,
            86_400,
        )


@asynccontextmanager
async def web_search_slot() -> AsyncIterator[None]:
    try:
        async with _web_search_limiter.slot(
            max(1, settings.WEB_SEARCH_CONCURRENCY),
            timeout_seconds=settings.WEB_SEARCH_TIMEOUT_SECONDS,
            kind="web_search",
        ):
            yield
    except TimeoutError as exc:
        raise SearchProviderError("search_concurrency_timeout") from exc
