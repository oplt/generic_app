import unittest
from unittest.mock import AsyncMock, patch
import asyncio

from backend.core.cache import (
    OBSERVABILITY_STATUS_CACHE_KEY,
    PLATFORM_EMAIL_TEMPLATES_CACHE_KEY,
    SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
    SETTINGS_DATABASE_CACHE_KEY,
    _local_cache,
    cache_get_json,
    cache_set_json,
    get_local_cached_json,
    invalidate_settings_config_cache,
)
from backend.modules.settings.schemas import ConfigSettingsResponse
from backend.modules.settings.service import SettingsService


class SettingsCacheTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _local_cache.delete(
            SETTINGS_DATABASE_CACHE_KEY,
            SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
            PLATFORM_EMAIL_TEMPLATES_CACHE_KEY,
            OBSERVABILITY_STATUS_CACHE_KEY,
        )

    async def test_list_database_settings_uses_shared_cache_loader(self):
        db = AsyncMock()
        service = SettingsService(db)
        cached_payload = [
            {
                "id": "setting-1",
                "key": "platform.app_name",
                "value": "Demo",
                "description": None,
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        service._load_database_settings_for_cache = AsyncMock(return_value=cached_payload)

        with patch(
            "backend.modules.settings.service.cache_get_or_load_json",
            AsyncMock(side_effect=[cached_payload, cached_payload]),
        ) as cache_get:
            first = await service.list_database_settings()
            second = await service.list_database_settings()

        self.assertEqual(first[0].key, "platform.app_name")
        self.assertEqual(second[0].key, "platform.app_name")
        self.assertEqual(cache_get.await_count, 2)
        service._load_database_settings_for_cache.assert_not_called()

    def test_list_config_entries_uses_local_cache(self):
        expected = ConfigSettingsResponse(items=[], notice="notice")

        with patch.object(
            SettingsService,
            "_build_config_entries",
            return_value=expected,
        ) as build:
            first = asyncio.run(SettingsService.list_config_entries())
            second = asyncio.run(SettingsService.list_config_entries())

        self.assertEqual(first.notice, second.notice)
        build.assert_called_once()

    def test_invalidate_settings_config_cache_clears_entries(self):
        from backend.core.cache import set_local_cached_json

        set_local_cached_json(
            SETTINGS_CONFIG_ENTRIES_CACHE_KEY,
            {"items": [], "notice": "notice"},
            ttl_seconds=60,
        )
        invalidate_settings_config_cache()
        self.assertIsNone(get_local_cached_json(SETTINGS_CONFIG_ENTRIES_CACHE_KEY))

    async def test_settings_local_cache_avoids_second_redis_read(self):
        payload = [{"id": "setting-1", "key": "demo", "value": "1"}]
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)

        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", redis_client),
        ):
            mock_settings.CACHE_ENABLED = True
            mock_settings.CACHE_SETTINGS_TTL_SECONDS = 60

            await cache_set_json(SETTINGS_DATABASE_CACHE_KEY, payload, ttl_seconds=60)
            redis_client.get.reset_mock()

            first = await cache_get_json(SETTINGS_DATABASE_CACHE_KEY)
            second = await cache_get_json(SETTINGS_DATABASE_CACHE_KEY)

        self.assertEqual(first, payload)
        self.assertEqual(second, payload)
        redis_client.get.assert_not_awaited()

    async def test_observability_status_uses_local_only_cache(self):
        from backend.observability.schemas import ObservabilityStatus, ObservabilityStatusItem
        from backend.observability.service import ObservabilityService

        item = ObservabilityStatusItem(
            status="healthy",
            detail="ok",
            last_checked_at="2026-01-01T00:00:00+00:00",
        )
        status = ObservabilityStatus(
            api=item,
            frontend=item,
            database=item,
            cache=item,
            workers=item,
            background_jobs=item,
            error_rate=item,
            request_latency=item,
            prometheus=item,
            grafana=item,
            tempo=item,
        )
        service = ObservabilityService(
            type("Settings", (), {"CACHE_OBSERVABILITY_STATUS_TTL_SECONDS": 30})()
        )
        service._build_status = AsyncMock(return_value=status)
        redis_client = AsyncMock()

        with patch("backend.core.cache.redis_client", redis_client):
            first = await service.get_status()
            second = await service.get_status()

        self.assertEqual(first.api.status, "healthy")
        self.assertEqual(second.api.status, "healthy")
        service._build_status.assert_awaited_once()
        redis_client.get.assert_not_awaited()
        redis_client.setex.assert_not_awaited()
