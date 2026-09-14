from __future__ import annotations

import logging
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request
from prometheus_client import Counter
from redis.exceptions import RedisError

from backend.core.cache import redis_client

logger = logging.getLogger(__name__)

_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""
_LOCAL_FALLBACK_MAX_KEYS = 10_000
_local_fallback: dict[str, tuple[int, float]] = {}
_local_fallback_lock = Lock()
rate_limit_fallback_total = Counter(
    "rate_limit_fallback_total",
    "Rate-limit operations served by the bounded local fallback",
)


def _build_rate_limit_exception(ttl: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Too many attempts. Try again in {max(1, ttl)} seconds.",
        headers={"Retry-After": str(max(1, ttl))},
    )


def _local_increment(key: str, window_seconds: int) -> tuple[int, int]:
    now = monotonic()
    with _local_fallback_lock:
        count, expires_at = _local_fallback.get(key, (0, now))
        if expires_at <= now:
            count, expires_at = 0, now + window_seconds
        count += 1
        _local_fallback[key] = (count, expires_at)
        if len(_local_fallback) > _LOCAL_FALLBACK_MAX_KEYS:
            oldest_key = min(_local_fallback, key=lambda item: _local_fallback[item][1])
            _local_fallback.pop(oldest_key, None)
        return count, max(1, int(expires_at - now))


def _local_read(key: str) -> tuple[int, int] | None:
    now = monotonic()
    with _local_fallback_lock:
        entry = _local_fallback.get(key)
        if entry is None:
            return None
        count, expires_at = entry
        if expires_at <= now:
            _local_fallback.pop(key, None)
            return None
        return count, max(1, int(expires_at - now))


async def _increment_with_ttl(key: str, window_seconds: int) -> tuple[int, int]:
    try:
        count = int(await redis_client.eval(_RATE_LIMIT_SCRIPT, 1, key, window_seconds))
        ttl = int(await redis_client.ttl(key))
        return count, max(1, ttl)
    except (RedisError, OSError, TimeoutError) as exc:
        rate_limit_fallback_total.inc()
        logger.warning(
            "Redis rate limiting unavailable; using bounded local fallback",
            exc_info=exc,
        )
        return _local_increment(key, window_seconds)


async def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    count, ttl = await _increment_with_ttl(key, window_seconds)
    if count > max_attempts:
        raise _build_rate_limit_exception(ttl)


async def enforce_rate_limit(key: str, max_attempts: int) -> None:
    try:
        raw_count = await redis_client.get(key)
        if raw_count is None:
            return
        count = int(raw_count)
        ttl = int(await redis_client.ttl(key))
    except (RedisError, OSError, TimeoutError) as exc:
        rate_limit_fallback_total.inc()
        logger.warning(
            "Redis rate limiting unavailable; reading bounded local fallback",
            exc_info=exc,
        )
        fallback = _local_read(key)
        if fallback is None:
            return
        count, ttl = fallback
    if count > max_attempts:
        raise _build_rate_limit_exception(ttl)


async def increment_rate_limit(key: str, window_seconds: int) -> int:
    count, _ = await _increment_with_ttl(key, window_seconds)
    return count


async def clear_rate_limit(key: str) -> None:
    try:
        await redis_client.delete(key)
    except (RedisError, OSError, TimeoutError) as exc:
        rate_limit_fallback_total.inc()
        logger.warning("Redis rate-limit clear unavailable; clearing local fallback", exc_info=exc)
    with _local_fallback_lock:
        _local_fallback.pop(key, None)


def auth_rate_limit_key(request: Request, email: str) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"rate_limit:auth:{client_ip}:{email}"
