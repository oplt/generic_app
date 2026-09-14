"""Phase 4: worker readiness caching + capability-scoped queues."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from backend.modules.platform.profiles import resolve_active_modules
from backend.workers import readiness as readiness_mod


class RequiredQueuesTest(unittest.TestCase):
    def test_core_profile_omits_specialist_queues(self) -> None:
        resolution = resolve_active_modules("core")
        with patch.object(readiness_mod, "resolve_active_modules", return_value=resolution):
            queues = readiness_mod._required_queues()
        self.assertIn("email", queues)
        self.assertIn("default", queues)
        self.assertNotIn("memory", queues)
        self.assertNotIn("ingestion", queues)
        self.assertNotIn("evaluation", queues)

    def test_agent_profile_includes_memory_queue(self) -> None:
        resolution = resolve_active_modules("agent")
        with patch.object(readiness_mod, "resolve_active_modules", return_value=resolution):
            queues = readiness_mod._required_queues()
        self.assertIn("memory", queues)
        self.assertIn("ingestion", queues)


class WorkerReadinessCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_cache_hit_skips_probe(self) -> None:
        cached = {
            "status": "ok",
            "detail": "from-cache",
            "queue_depth": 3,
            "oldest_job_age_seconds": 1.5,
            "retry_count": 0,
            "failed_job_count": 0,
            "last_successful_heartbeat_at": "2026-09-14T00:00:00+00:00",
            "queue_depths": {"default": 1, "email": 2},
        }
        probe = AsyncMock(side_effect=AssertionError("probe must not run on hit"))
        with (
            patch.object(readiness_mod, "_probe_worker_readiness", probe),
            patch.object(readiness_mod, "_required_queues", return_value=("default", "email")),
            patch(
                "backend.workers.readiness.cache_get_or_load_json",
                new_callable=AsyncMock,
                return_value=cached,
            ),
        ):
            result = await readiness_mod.worker_readiness()
        self.assertEqual(result.detail, "from-cache")
        self.assertEqual(result.queue_depth, 3)
        probe.assert_not_awaited()

    async def test_cache_loader_receives_probe_and_ttl(self) -> None:
        probe = AsyncMock(
            return_value={
                "status": "ok",
                "detail": "probed",
                "queue_depth": 0,
                "oldest_job_age_seconds": None,
                "retry_count": 0,
                "failed_job_count": 0,
                "last_successful_heartbeat_at": "2026-09-14T00:00:00+00:00",
                "queue_depths": {"default": 0, "email": 0},
            }
        )

        async def fake_cache(key, *, ttl_seconds, loader):
            self.assertEqual(key, readiness_mod.WORKER_READINESS_CACHE_KEY)
            self.assertEqual(ttl_seconds, readiness_mod.WORKER_READINESS_CACHE_TTL_SECONDS)
            return await loader()

        with (
            patch.object(readiness_mod, "_probe_worker_readiness", probe),
            patch.object(readiness_mod, "_required_queues", return_value=("default", "email")),
            patch(
                "backend.workers.readiness.cache_get_or_load_json",
                side_effect=fake_cache,
            ),
        ):
            result = await readiness_mod.worker_readiness()
        self.assertEqual(result.detail, "probed")
        probe.assert_awaited_once()


class StartupHealthChecksTest(unittest.TestCase):
    def test_core_does_not_require_storage_or_vector(self) -> None:
        resolution = resolve_active_modules("core")
        self.assertNotIn("storage", resolution.health_checks)
        self.assertNotIn("vector", resolution.health_checks)

    def test_rag_requires_storage_and_vector(self) -> None:
        resolution = resolve_active_modules("rag")
        self.assertIn("storage", resolution.health_checks)
        self.assertIn("vector", resolution.health_checks)
