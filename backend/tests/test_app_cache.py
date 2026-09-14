"""Tests for the standardized application cache abstraction."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.lib.app_cache import CacheScope, app_cache, build_cache_key, namespaces
from backend.lib.app_cache.keys import hash_cache_part


class AppCacheKeyTest(unittest.TestCase):
    def test_scoped_keys_isolate_tenants(self) -> None:
        org_a = build_cache_key(
            namespaces.PERMISSIONS,
            "can_read",
            scope=CacheScope(organization_id="org-a", user_id="user-1"),
        )
        org_b = build_cache_key(
            namespaces.PERMISSIONS,
            "can_read",
            scope=CacheScope(organization_id="org-b", user_id="user-1"),
        )
        self.assertNotEqual(org_a, org_b)
        self.assertIn(":org:org-a:", org_a)
        self.assertIn(":org:org-b:", org_b)

    def test_hash_avoids_raw_sensitive_parts(self) -> None:
        digest = hash_cache_part("secret-query", "token")
        key = build_cache_key(namespaces.RETRIEVAL, digest)
        self.assertNotIn("secret-query", key)
        self.assertIn(digest, key)

    def test_rejects_unsafe_raw_parts(self) -> None:
        with self.assertRaises(ValueError):
            build_cache_key(namespaces.RETRIEVAL, "raw query with spaces")


class AppCacheServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_or_set_singleflight_stampede(self) -> None:
        store: dict[str, object] = {}
        loader_calls = 0
        key = build_cache_key(namespaces.SETTINGS, "stampede")

        async def get_json(cache_key: str):
            return store.get(cache_key)

        async def set_json(cache_key: str, value, *, ttl_seconds: int):
            del ttl_seconds
            store[cache_key] = value

        async def loader():
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.02)
            return {"value": 1}

        with (
            patch("backend.core.cache.cache_get_json", side_effect=get_json),
            patch("backend.core.cache.cache_set_json", side_effect=set_json),
            patch("backend.core.cache._uses_redis_cache", return_value=False),
            patch("backend.core.cache.settings") as mock_settings,
        ):
            mock_settings.CACHE_ENABLED = True
            values = await asyncio.gather(
                app_cache.get_or_set(key, loader, ttl_seconds=30),
                app_cache.get_or_set(key, loader, ttl_seconds=30),
                app_cache.get_or_set(key, loader, ttl_seconds=30),
            )

        self.assertEqual(loader_calls, 1)
        self.assertEqual(values, [{"value": 1}, {"value": 1}, {"value": 1}])

    async def test_negative_caching_skips_loader(self) -> None:
        key = build_cache_key(namespaces.FEATURE_FLAGS, "missing")
        loader = AsyncMock(return_value={"should": "not-run"})

        with (
            patch(
                "backend.core.cache.cache_get_json",
                AsyncMock(return_value={"__ga_cache_negative__": True}),
            ),
            patch("backend.core.cache.cache_set_json", AsyncMock()) as cache_set,
            patch("backend.core.cache._uses_redis_cache", return_value=False),
        ):
            value = await app_cache.get_or_set(key, loader, ttl_seconds=30)

        self.assertIsNone(value)
        loader.assert_not_awaited()
        cache_set.assert_not_awaited()

    async def test_get_or_set_can_store_negative_miss(self) -> None:
        store: dict[str, object] = {}
        key = build_cache_key(namespaces.AUTH, "session-miss")

        async def get_json(cache_key: str):
            return store.get(cache_key)

        async def set_json(cache_key: str, value, *, ttl_seconds: int):
            del ttl_seconds
            store[cache_key] = value

        with (
            patch("backend.core.cache.cache_get_json", side_effect=get_json),
            patch("backend.core.cache.cache_set_json", side_effect=set_json),
            patch("backend.core.cache._uses_redis_cache", return_value=False),
            patch("backend.core.cache.settings") as mock_settings,
        ):
            mock_settings.CACHE_ENABLED = True
            first = await app_cache.get_or_set(
                key,
                AsyncMock(return_value=None),
                ttl_seconds=60,
                cache_none=True,
                none_ttl_seconds=15,
            )
            second = await app_cache.get(key)

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(store[key], {"__ga_cache_negative__": True})

    async def test_invalidate_tags_deletes_members(self) -> None:
        client = AsyncMock()
        client.smembers = AsyncMock(return_value={"ga:v1:settings:org:_:user:_:project:_:a"})
        client.delete = AsyncMock()

        with (
            patch("backend.core.cache.redis_client", client),
            patch("backend.core.cache.cache_delete", AsyncMock()) as cache_delete,
            patch("backend.core.cache.settings") as mock_settings,
        ):
            mock_settings.CACHE_ENABLED = True
            await app_cache.invalidate_tags("settings:org:org-1")

        cache_delete.assert_awaited_once_with(
            "ga:v1:settings:org:_:user:_:project:_:a"
        )
        client.delete.assert_awaited()

    async def test_set_registers_tags(self) -> None:
        client = AsyncMock()
        key = build_cache_key(namespaces.SETTINGS, "flag-x")

        with (
            patch("backend.core.cache.cache_set_json", AsyncMock()) as cache_set,
            patch("backend.core.cache.redis_client", client),
            patch("backend.core.cache.settings") as mock_settings,
        ):
            mock_settings.CACHE_ENABLED = True
            await app_cache.set(
                key,
                {"on": True},
                ttl_seconds=30,
                tags=["settings:org:org-1"],
            )

        cache_set.assert_awaited_once()
        client.sadd.assert_awaited_once_with("ga:tag:settings:org:org-1", key)
        client.expire.assert_awaited_once()

    async def test_redis_failure_fail_open_on_get(self) -> None:
        with patch(
            "backend.core.cache.cache_get_json",
            AsyncMock(return_value=None),
        ):
            value = await app_cache.get(build_cache_key(namespaces.PLATFORM, "config"))
        self.assertIsNone(value)

    async def test_set_fail_open_does_not_raise(self) -> None:
        with (
            patch(
                "backend.core.cache.cache_set_json",
                AsyncMock(side_effect=RuntimeError("redis down")),
            ),
            patch("backend.core.cache.settings") as mock_settings,
        ):
            mock_settings.CACHE_ENABLED = True
            await app_cache.set(
                build_cache_key(namespaces.PLATFORM, "config"),
                {"ok": True},
                ttl_seconds=10,
            )
