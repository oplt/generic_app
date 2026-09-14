from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, TypeVar

import redis.asyncio as redis
from prometheus_client import Counter, Histogram
from pydantic import BaseModel

from backend.core.cache_loader import coordinated_cache_load
from backend.core.config import settings

logger = logging.getLogger(__name__)

cache_hits_total = Counter(
    "cache_hits_total", "Cache hits by namespace", ["namespace"]
)
cache_misses_total = Counter(
    "cache_misses_total", "Cache misses by namespace", ["namespace"]
)
cache_errors_total = Counter(
    "cache_errors_total", "Cache backend or payload errors", ["namespace"]
)
cache_stale_total = Counter(
    "cache_stale_total", "Expired or invalid cache payloads", ["namespace"]
)
cache_invalidations_total = Counter(
    "cache_invalidations_total", "Cache invalidations by namespace", ["namespace"]
)
cache_payload_bytes = Histogram(
    "cache_payload_bytes", "Approximate serialized cache payload size", ["namespace"]
)

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

CACHE_NAMESPACE = "ga"
PLATFORM_CONFIG_CACHE_KEY = f"{CACHE_NAMESPACE}:platform:config"
PLATFORM_FEATURE_FLAGS_CACHE_KEY = f"{CACHE_NAMESPACE}:platform:feature_flags"
SETTINGS_DATABASE_CACHE_KEY = f"{CACHE_NAMESPACE}:settings:database:all"
SETTINGS_CONFIG_ENTRIES_CACHE_KEY = f"{CACHE_NAMESPACE}:settings:config_entries"
PLATFORM_EMAIL_TEMPLATES_CACHE_KEY = f"{CACHE_NAMESPACE}:platform:email_templates"
OBSERVABILITY_STATUS_CACHE_KEY = f"{CACHE_NAMESPACE}:observability:status"
LOCAL_CACHE_KEYS = frozenset(
    {
        PLATFORM_CONFIG_CACHE_KEY,
        PLATFORM_FEATURE_FLAGS_CACHE_KEY,
        SETTINGS_DATABASE_CACHE_KEY,
        SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
        PLATFORM_EMAIL_TEMPLATES_CACHE_KEY,
        OBSERVABILITY_STATUS_CACHE_KEY,
    }
)
LOCAL_ONLY_CACHE_KEYS = frozenset(
    {
        SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
        OBSERVABILITY_STATUS_CACHE_KEY,
    }
)

T = TypeVar("T")


class _LocalTTLCache:
    __slots__ = ("_entries", "_maxsize")

    def __init__(self, maxsize: int = 64):
        self._maxsize = maxsize
        self._entries: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if monotonic() >= expires_at:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        self._entries[key] = (value, monotonic() + ttl_seconds)
        self._entries.move_to_end(key)
        while len(self._entries) > self._maxsize:
            self._entries.popitem(last=False)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self._entries.pop(key, None)


_local_cache = _LocalTTLCache()
_local_generations: dict[str, int] = {}


def _cache_namespace(key: str) -> str:
    parts = key.split(":")
    return parts[1] if len(parts) > 1 else "unknown"


def _uses_local_cache(key: str) -> bool:
    return key in LOCAL_CACHE_KEYS


def _uses_redis_cache(key: str) -> bool:
    if key in LOCAL_ONLY_CACHE_KEYS:
        return False
    return settings.CACHE_ENABLED


def _local_ttl_for_key(key: str) -> int:
    if key == OBSERVABILITY_STATUS_CACHE_KEY:
        return settings.CACHE_OBSERVABILITY_STATUS_TTL_SECONDS
    if key in {
        SETTINGS_DATABASE_CACHE_KEY,
        SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
        PLATFORM_EMAIL_TEMPLATES_CACHE_KEY,
    }:
        return settings.CACHE_SETTINGS_TTL_SECONDS
    if key.startswith(f"{CACHE_NAMESPACE}:platform:"):
        return settings.CACHE_PLATFORM_TTL_SECONDS
    return 60


def get_local_cached_json(key: str) -> Any | None:
    if not _uses_local_cache(key):
        return None
    return _local_cache.get(key)


def set_local_cached_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    if _uses_local_cache(key):
        _local_cache.set(key, value, ttl_seconds=ttl_seconds)


def delete_local_cached_json(*keys: str) -> None:
    if keys:
        _local_cache.delete(*keys)


def cache_key(*parts: str) -> str:
    return ":".join((CACHE_NAMESPACE, *parts))


def embedding_cache_key(
    provider: str,
    model: str,
    text: str,
    *,
    dimensions: int | None = None,
) -> str:
    resolved_dimensions = (
        dimensions if dimensions is not None else settings.RAG_EMBEDDING_DIMENSIONS
    )
    digest = hashlib.sha256(
        f"{provider}\0{model}\0{resolved_dimensions}\0{text}".encode()
    ).hexdigest()
    return cache_key("embed", digest)


async def cache_get_json(key: str) -> Any | None:
    from backend.lib.failure_injection import should_force_cache_miss

    if should_force_cache_miss():
        return None

    if _uses_local_cache(key):
        local_value = _local_cache.get(key)
        if local_value is not None:
            cache_hits_total.labels(namespace=_cache_namespace(key)).inc()
            try:
                from backend.observability.request_diagnostics import record_cache_hit

                record_cache_hit()
            except Exception:
                pass
            return local_value

    if not _uses_redis_cache(key):
        return None
    try:
        from backend.lib.failure_injection import maybe_inject
        from backend.lib.failure_injection.kinds import FaultKind

        maybe_inject(FaultKind.REDIS_UNAVAILABLE)
        maybe_inject(FaultKind.REDIS_TIMEOUT)
        raw = await redis_client.get(key)
        if raw is None:
            cache_misses_total.labels(namespace=_cache_namespace(key)).inc()
            try:
                from backend.observability.request_diagnostics import record_cache_miss

                record_cache_miss()
            except Exception:
                pass
            return None
        value = json.loads(raw)
        cache_hits_total.labels(namespace=_cache_namespace(key)).inc()
        try:
            from backend.observability.request_diagnostics import record_cache_hit

            record_cache_hit()
        except Exception:
            pass
        if _uses_local_cache(key):
            _local_cache.set(key, value, ttl_seconds=_local_ttl_for_key(key))
        return value
    except json.JSONDecodeError:
        cache_stale_total.labels(namespace=_cache_namespace(key)).inc()
        cache_errors_total.labels(namespace=_cache_namespace(key)).inc()
        logger.debug("cache payload invalid for key=%s", key, exc_info=True)
        return None
    except Exception:
        cache_errors_total.labels(namespace=_cache_namespace(key)).inc()
        logger.debug("cache get failed for key=%s", key, exc_info=True)
        return None


async def cache_get_many_json(keys: list[str]) -> dict[str, Any]:
    """Read multiple cache entries in one Redis round trip when possible."""
    if not keys:
        return {}

    values: dict[str, Any] = {}
    redis_keys: list[str] = []
    for key in keys:
        if _uses_local_cache(key):
            local_value = _local_cache.get(key)
            if local_value is not None:
                values[key] = local_value
                continue
        if _uses_redis_cache(key):
            redis_keys.append(key)

    if not redis_keys:
        return values

    try:
        raw_values = await redis_client.mget(redis_keys)
        for key, raw in zip(redis_keys, raw_values, strict=True):
            if raw is None:
                continue
            value = json.loads(raw)
            values[key] = value
            if _uses_local_cache(key):
                _local_cache.set(key, value, ttl_seconds=_local_ttl_for_key(key))
    except json.JSONDecodeError:
        cache_stale_total.labels(namespace=_cache_namespace(redis_keys[0])).inc()
        cache_errors_total.labels(namespace=_cache_namespace(redis_keys[0])).inc()
        logger.debug("cache batch payload invalid for keys=%s", redis_keys, exc_info=True)
    except Exception:
        cache_errors_total.labels(namespace=_cache_namespace(redis_keys[0])).inc()
        logger.debug("cache batch get failed for keys=%s", redis_keys, exc_info=True)
    return values


async def cache_set_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    if _uses_local_cache(key):
        _local_cache.set(key, value, ttl_seconds=ttl_seconds)
    if not _uses_redis_cache(key):
        return
    try:
        serialized = json.dumps(value, ensure_ascii=True, default=str)
        if len(serialized.encode("utf-8")) > settings.CACHE_MAX_PAYLOAD_BYTES:
            cache_errors_total.labels(namespace=_cache_namespace(key)).inc()
            logger.warning(
                "cache payload exceeds configured limit key=%s bytes=%s",
                key,
                len(serialized.encode("utf-8")),
            )
            return
        cache_payload_bytes.labels(namespace=_cache_namespace(key)).observe(len(serialized))
        await redis_client.setex(
            key,
            ttl_seconds,
            serialized,
        )
    except Exception:
        cache_errors_total.labels(namespace=_cache_namespace(key)).inc()
        logger.debug("cache set failed for key=%s", key, exc_info=True)


async def cache_set_many_json(entries: list[tuple[str, Any, int]]) -> None:
    """Write multiple cache entries with one Redis pipeline when possible."""
    if not entries:
        return

    redis_entries: list[tuple[str, Any, int]] = []
    for key, value, ttl_seconds in entries:
        if _uses_local_cache(key):
            _local_cache.set(key, value, ttl_seconds=ttl_seconds)
        if _uses_redis_cache(key):
            redis_entries.append((key, value, ttl_seconds))

    if not redis_entries:
        return

    try:
        pipeline = redis_client.pipeline(transaction=False)
        for key, value, ttl_seconds in redis_entries:
            serialized = json.dumps(value, ensure_ascii=True, default=str)
            if len(serialized.encode("utf-8")) > settings.CACHE_MAX_PAYLOAD_BYTES:
                cache_errors_total.labels(namespace=_cache_namespace(key)).inc()
                logger.warning("cache payload exceeds configured limit key=%s", key)
                continue
            cache_payload_bytes.labels(namespace=_cache_namespace(key)).observe(len(serialized))
            pipeline.setex(
                key,
                ttl_seconds,
                serialized,
            )
        await pipeline.execute()
    except Exception:
        cache_errors_total.labels(namespace=_cache_namespace(redis_entries[0][0])).inc()
        logger.debug(
            "cache batch set failed for keys=%s",
            [key for key, _, _ in redis_entries],
            exc_info=True,
        )


async def cache_delete(*keys: str) -> None:
    if keys:
        _local_cache.delete(*keys)
        for key in keys:
            cache_invalidations_total.labels(namespace=_cache_namespace(key)).inc()
    redis_keys = [key for key in keys if _uses_redis_cache(key)]
    if not redis_keys:
        return
    try:
        await redis_client.delete(*redis_keys)
    except Exception:
        cache_errors_total.labels(namespace=_cache_namespace(redis_keys[0])).inc()
        logger.debug("cache delete failed for keys=%s", redis_keys, exc_info=True)


async def cache_delete_pattern(pattern: str, *, batch_size: int = 100) -> None:
    if not settings.CACHE_ENABLED:
        return
    try:
        cache_invalidations_total.labels(namespace=_cache_namespace(pattern)).inc()
        batch: list[str] = []
        async for key in redis_client.scan_iter(match=pattern, count=batch_size):
            batch.append(key)
            if len(batch) >= batch_size:
                await redis_client.delete(*batch)
                batch.clear()
        if batch:
            await redis_client.delete(*batch)
    except Exception:
        cache_errors_total.labels(namespace=_cache_namespace(pattern)).inc()
        logger.debug("cache delete pattern failed for pattern=%s", pattern, exc_info=True)


async def cache_get_generation(scope: str) -> int:
    key = cache_key("generation", scope)
    if settings.CACHE_ENABLED:
        try:
            raw = await redis_client.get(key)
            if raw is not None:
                return int(raw)
        except Exception:
            cache_errors_total.labels(namespace="generation").inc()
            logger.debug("cache generation read failed for scope=%s", scope, exc_info=True)
    return _local_generations.get(scope, 0)


async def cache_bump_generation(scope: str) -> int:
    key = cache_key("generation", scope)
    next_value = _local_generations.get(scope, 0) + 1
    _local_generations[scope] = next_value
    if settings.CACHE_ENABLED:
        try:
            next_value = int(await redis_client.incr(key))
            await redis_client.expire(key, settings.CACHE_RETRIEVAL_TTL_SECONDS * 10)
            _local_generations[scope] = next_value
        except Exception:
            cache_errors_total.labels(namespace="generation").inc()
            logger.debug("cache generation bump failed for scope=%s", scope, exc_info=True)
    cache_invalidations_total.labels(namespace="generation").inc()
    return next_value


async def cache_get_model(key: str, model: type[T]) -> T | None:  # noqa: UP047
    payload = await cache_get_json(key)
    if payload is None:
        return None
    if isinstance(model, type) and issubclass(model, BaseModel):
        return model.model_validate(payload)
    return payload


async def cache_set_model(key: str, value: BaseModel, *, ttl_seconds: int) -> None:
    await cache_set_json(key, value.model_dump(mode="json"), ttl_seconds=ttl_seconds)


async def cache_get_or_load_model[T](
    key: str,
    model: type[T],
    *,
    ttl_seconds: int,
    loader: Callable[[], Awaitable[T]],
) -> T:
    async def get_cached() -> T | None:
        return await cache_get_model(key, model)

    async def set_loaded(value: T) -> None:
        if isinstance(value, BaseModel):
            await cache_set_model(key, value, ttl_seconds=ttl_seconds)

    return await coordinated_cache_load(
        key,
        kind="model",
        get_cached=get_cached,
        set_loaded=set_loaded,
        loader=loader,
        redis_client=redis_client,
        redis_enabled=_uses_redis_cache,
    )


async def cache_get_or_load_json(
    key: str,
    *,
    ttl_seconds: int,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    async def get_cached() -> Any | None:
        return await cache_get_json(key)

    async def set_loaded(value: Any) -> None:
        await cache_set_json(key, value, ttl_seconds=ttl_seconds)

    return await coordinated_cache_load(
        key,
        kind="json",
        get_cached=get_cached,
        set_loaded=set_loaded,
        loader=loader,
        redis_client=redis_client,
        redis_enabled=_uses_redis_cache,
    )


async def invalidate_platform_caches() -> None:
    await cache_delete(PLATFORM_CONFIG_CACHE_KEY, PLATFORM_FEATURE_FLAGS_CACHE_KEY)


async def invalidate_platform_email_template_cache() -> None:
    await cache_delete(PLATFORM_EMAIL_TEMPLATES_CACHE_KEY)


async def invalidate_settings_database_cache() -> None:
    await cache_delete(SETTINGS_DATABASE_CACHE_KEY, SETTINGS_CONFIG_ENTRIES_CACHE_KEY)


def invalidate_settings_config_cache() -> None:
    delete_local_cached_json(SETTINGS_CONFIG_ENTRIES_CACHE_KEY)


async def invalidate_settings_related_caches(setting_key: str | None = None) -> None:
    await invalidate_settings_database_cache()
    if setting_key is None or setting_key.startswith("platform."):
        await invalidate_platform_caches()
