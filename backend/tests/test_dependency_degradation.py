"""Failure-injection coverage for dependency degradation and beat overlap."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from backend.api.v1.health import _readiness_response, dependency_operational_state
from backend.core.cache import cache_get_json
from backend.core.rate_limit import check_rate_limit
from backend.modules.chat.application.conversation_service import ConversationService
from backend.workers.schedule_lock import (
    release_beat_lock,
    try_acquire_beat_lock,
    try_acquire_chat_retention_advisory_lock,
)


class DependencyStateMappingTest(unittest.TestCase):
    def test_maps_readiness_values_to_operational_states(self):
        self.assertEqual(dependency_operational_state("ok"), "healthy")
        self.assertEqual(dependency_operational_state("error"), "unavailable")
        self.assertEqual(dependency_operational_state("not_required"), "not_required")
        self.assertEqual(dependency_operational_state("unknown"), "unknown")

    def test_multi_dependency_degradation_lists_failed_required_checks(self):
        with self.assertRaises(HTTPException) as context:
            _readiness_response(
                {
                    "db": "ok",
                    "redis": "error",
                    "queue": "error",
                    "storage": "error",
                    "vector": "ok",
                },
                required_checks={"db", "redis", "queue", "storage", "vector"},
            )
        self.assertEqual(context.exception.status_code, 503)
        detail = context.exception.detail
        self.assertEqual(detail["status"], "degraded")
        self.assertEqual(
            detail["failed_required_checks"],
            ["queue", "redis", "storage"],
        )
        self.assertEqual(detail["dependency_states"]["redis"], "unavailable")
        self.assertEqual(detail["dependency_states"]["vector"], "healthy")


class CacheFailOpenTest(unittest.IsolatedAsyncioTestCase):
    async def test_cache_get_returns_none_when_redis_errors(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=TimeoutError("redis down"))
        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", client),
            patch("backend.core.cache._uses_local_cache", return_value=False),
            patch("backend.core.cache._uses_redis_cache", return_value=True),
        ):
            mock_settings.CACHE_ENABLED = True
            value = await cache_get_json("ga:dep-fail")
        self.assertIsNone(value)


class RateLimitFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_uses_bounded_local_fallback_when_redis_down(self):
        client = AsyncMock()
        client.eval = AsyncMock(side_effect=TimeoutError("redis down"))
        key = "ga:rate:dep-fail-unique"
        with patch("backend.core.rate_limit.redis_client", client):
            await check_rate_limit(key, max_attempts=2, window_seconds=60)
            await check_rate_limit(key, max_attempts=2, window_seconds=60)
            with self.assertRaises(HTTPException) as context:
                await check_rate_limit(key, max_attempts=2, window_seconds=60)
        self.assertEqual(context.exception.status_code, 429)


class BeatScheduleLockTest(unittest.IsolatedAsyncioTestCase):
    async def test_second_acquire_skipped_while_lock_held(self):
        store: dict[str, str] = {}

        async def set_nx(key, value, *, nx=False, ex=None):
            if nx and key in store:
                return False
            store[key] = value
            return True

        async def eval_script(_script, _num_keys, key, token):
            if store.get(key) == token:
                del store[key]
                return 1
            return 0

        client = AsyncMock()
        client.set = AsyncMock(side_effect=set_nx)
        client.eval = AsyncMock(side_effect=eval_script)
        with (
            patch("backend.workers.schedule_lock.redis_client", client),
            patch("backend.workers.schedule_lock.settings") as mock_settings,
        ):
            mock_settings.WORKER_BEAT_OUTBOX_LOCK_TTL_SECONDS = 55
            first, second = await asyncio.gather(
                try_acquire_beat_lock("outbox-dispatch"),
                try_acquire_beat_lock("outbox-dispatch"),
            )
            self.assertTrue(bool(first) ^ bool(second))
            winner = first or second
            await release_beat_lock("outbox-dispatch", winner)
            third = await try_acquire_beat_lock("outbox-dispatch")
        self.assertIsNotNone(third)

    async def test_redis_error_fail_opens_when_configured(self):
        client = AsyncMock()
        client.set = AsyncMock(side_effect=TimeoutError("redis down"))
        with patch("backend.workers.schedule_lock.redis_client", client):
            token = await try_acquire_beat_lock("outbox-dispatch", on_redis_error="proceed")
            skipped = await try_acquire_beat_lock("chat-retention", on_redis_error="skip")
        self.assertIsNotNone(token)
        self.assertTrue(str(token).startswith("redis-unavailable:"))
        self.assertIsNone(skipped)
        await release_beat_lock("outbox-dispatch", token)


class ChatRetentionAdvisoryLockTest(unittest.IsolatedAsyncioTestCase):
    async def test_delete_expired_skips_when_advisory_lock_busy(self):
        db = AsyncMock()
        db.rollback = AsyncMock()
        db.commit = AsyncMock()
        service = ConversationService(db)
        service.repo = MagicMock()
        service.repo.delete_expired_conversations = AsyncMock(return_value=3)
        service.repo.delete_expired_messages = AsyncMock(return_value=2)

        with patch(
            "backend.workers.schedule_lock.try_acquire_chat_retention_advisory_lock",
            AsyncMock(return_value=False),
        ):
            deleted = await service.delete_expired()

        self.assertEqual(deleted, 0)
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()
        service.repo.delete_expired_conversations.assert_not_awaited()

    async def test_advisory_lock_helper_reads_postgres_scalar(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = True
        db.execute = AsyncMock(return_value=result)
        self.assertTrue(await try_acquire_chat_retention_advisory_lock(db))
        db.execute.assert_awaited_once()


class BeatTaskOverlapWiringTest(unittest.TestCase):
    def test_outbox_task_skips_dispatch_when_lock_held(self):
        from backend.workers import tasks as worker_tasks

        with (
            patch(
                "backend.workers.schedule_lock.try_acquire_beat_lock",
                AsyncMock(return_value=None),
            ),
            patch(
                "backend.workers.tasks.dispatch_pending_job_events",
                AsyncMock(return_value=7),
            ) as dispatch,
            patch(
                "backend.workers.tasks.run_tracked_sync",
                side_effect=lambda **kwargs: kwargs["runner"](),
            ),
            patch(
                "backend.workers.tasks.run_async_in_sync_context",
                side_effect=asyncio.run,
            ),
        ):
            result = worker_tasks.dispatch_outbox_task()
        self.assertEqual(result, 0)
        dispatch.assert_not_awaited()

    def test_chat_retention_task_skips_when_lock_held(self):
        from backend.workers import tasks as worker_tasks

        with (
            patch(
                "backend.workers.schedule_lock.try_acquire_beat_lock",
                AsyncMock(return_value=None),
            ),
            patch(
                "backend.workers.tasks.run_tracked_sync",
                side_effect=lambda **kwargs: kwargs["runner"](),
            ),
            patch(
                "backend.workers.tasks.run_async_in_sync_context",
                side_effect=asyncio.run,
            ),
        ):
            result = worker_tasks.cleanup_chat_retention_task()
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
