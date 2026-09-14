from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from time import monotonic
from typing import Any
from uuid import uuid4

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

_DISTRIBUTED_LOCK_TTL_SECONDS = 10
_DISTRIBUTED_LOCK_WAIT_SECONDS = 5.0
_DISTRIBUTED_LOCK_POLL_SECONDS = 0.05
_singleflight_locks: dict[str, asyncio.Lock] = {}
_LOCK_FILLED = object()
_LOCK_UNAVAILABLE = object()
_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

cache_loader_hit_total = Counter(
    "cache_loader_hit_total", "Cache loader requests served from cache", ["kind"]
)
cache_loader_miss_total = Counter(
    "cache_loader_miss_total", "Cache loader requests requiring load coordination", ["kind"]
)
cache_loader_latency_seconds = Histogram(
    "cache_loader_latency_seconds", "Cache loader execution latency", ["kind"]
)
cache_singleflight_wait_total = Counter(
    "cache_singleflight_wait_total",
    "Cache loader requests waiting on another process",
    ["kind"],
)


def _singleflight_lock(key: str) -> asyncio.Lock:
    return _singleflight_locks.setdefault(key, asyncio.Lock())


def _distributed_lock_key(key: str) -> str:
    return f"ga:lock:{hashlib.sha256(key.encode()).hexdigest()}"


async def _try_acquire_distributed_lock(
    key: str,
    *,
    redis_client: Any,
    redis_enabled: Callable[[str], bool],
) -> str | object | None:
    if not redis_enabled(key):
        return None
    token = uuid4().hex
    try:
        acquired = await redis_client.set(
            _distributed_lock_key(key), token, nx=True, ex=_DISTRIBUTED_LOCK_TTL_SECONDS
        )
    except Exception:
        logger.debug("distributed cache lock failed for key=%s", key, exc_info=True)
        return _LOCK_UNAVAILABLE
    return token if acquired else None


async def _release_distributed_lock(key: str, token: str | None, *, redis_client: Any) -> None:
    if token is None:
        return
    with suppress(Exception):
        await redis_client.eval(_RELEASE_LOCK_SCRIPT, 1, _distributed_lock_key(key), token)


async def _wait_for_distributed_lock(
    key: str,
    get_cached: Callable[[], Awaitable[Any]],
    *,
    redis_client: Any,
    redis_enabled: Callable[[str], bool],
) -> str | object | None:
    if not redis_enabled(key):
        return None
    deadline = monotonic() + _DISTRIBUTED_LOCK_WAIT_SECONDS
    while monotonic() < deadline:
        if await get_cached() is not None:
            return _LOCK_FILLED
        token = await _try_acquire_distributed_lock(
            key, redis_client=redis_client, redis_enabled=redis_enabled
        )
        if token is _LOCK_UNAVAILABLE:
            return _LOCK_UNAVAILABLE
        if token is not None:
            return token
        await asyncio.sleep(_DISTRIBUTED_LOCK_POLL_SECONDS)
    return None


async def coordinated_cache_load(
    key: str,
    *,
    kind: str,
    get_cached: Callable[[], Awaitable[Any]],
    set_loaded: Callable[[Any], Awaitable[None]],
    loader: Callable[[], Awaitable[Any]],
    redis_client: Any,
    redis_enabled: Callable[[str], bool],
) -> Any:
    cached = await get_cached()
    if cached is not None:
        cache_loader_hit_total.labels(kind=kind).inc()
        return cached
    cache_loader_miss_total.labels(kind=kind).inc()

    async with _singleflight_lock(key):
        cached = await get_cached()
        if cached is not None:
            cache_loader_hit_total.labels(kind=kind).inc()
            return cached
        lock_token = await _wait_for_distributed_lock(
            key,
            get_cached,
            redis_client=redis_client,
            redis_enabled=redis_enabled,
        )
        lock_unavailable = lock_token is _LOCK_UNAVAILABLE
        if lock_token is _LOCK_FILLED:
            cache_loader_hit_total.labels(kind=kind).inc()
            return await get_cached()
        if lock_unavailable:
            lock_token = None
        if lock_token is None and redis_enabled(key) and not lock_unavailable:
            cache_singleflight_wait_total.labels(kind=kind).inc()

        started = monotonic()
        try:
            loaded = await loader()
            await set_loaded(loaded)
            return loaded
        finally:
            cache_loader_latency_seconds.labels(kind=kind).observe(monotonic() - started)
            await _release_distributed_lock(
                key,
                lock_token if isinstance(lock_token, str) else None,
                redis_client=redis_client,
            )
