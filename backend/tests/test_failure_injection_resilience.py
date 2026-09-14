"""Deterministic resilience tests for controlled failure injection."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from backend.api.v1.health import _readiness_response, dependency_operational_state
from backend.core.cache import cache_get_json
from backend.core.storage import ObjectStorage
from backend.lib.failure_injection import (
    FaultKind,
    injecting,
    injection_permitted,
    maybe_inject,
    should_force_cache_miss,
)
from backend.lib.failure_injection.guard import FailureInjectionForbidden
from backend.lib.failure_injection.runtime import (
    InjectedFailure,
    assert_no_secrets,
    operational_state_for_fault,
)
from backend.modules.ai.provider_retry import post_with_retry
from backend.workers.async_dispatch import dispatch_background_sync_job
from backend.workers.email import _deliver_email


class ProductionGuardTest(unittest.TestCase):
    def test_injection_forbidden_in_production_context(self) -> None:
        with patch("backend.lib.failure_injection.guard.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.FAILURE_INJECTION_ENABLED = True
            with self.assertRaises(FailureInjectionForbidden):
                with injecting(FaultKind.REDIS_TIMEOUT):
                    pass

    def test_injection_permitted_false_in_production(self) -> None:
        with patch("backend.lib.failure_injection.guard.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.FAILURE_INJECTION_ENABLED = True
            self.assertFalse(injection_permitted())

    def test_config_rejects_injection_flag_in_production(self) -> None:
        from backend.core.config import Settings

        payload = Settings().model_dump()
        payload.update(
            {
                "APP_ENV": "production",
                "FAILURE_INJECTION_ENABLED": True,
                "COOKIE_SECURE": True,
                "CELERY_TASK_ALWAYS_EAGER": False,
                "CORS_ALLOWED_ORIGINS": ["https://example.com"],
                "FRONTEND_URL": "https://example.com",
            }
        )
        with self.assertRaises(ValueError):
            Settings(**payload)


class OperationalStateCatalogTest(unittest.TestCase):
    def test_faults_map_to_documented_states(self) -> None:
        self.assertEqual(
            operational_state_for_fault(FaultKind.REDIS_UNAVAILABLE), "unavailable"
        )
        self.assertEqual(
            operational_state_for_fault(FaultKind.REDIS_CACHE_MISS_STORM), "degraded"
        )
        self.assertEqual(dependency_operational_state("error"), "unavailable")
        self.assertEqual(dependency_operational_state("ok"), "healthy")


class RedisInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_redis_unavailable_fails_open_to_miss(self) -> None:
        with (
            injecting(FaultKind.REDIS_UNAVAILABLE),
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache._uses_local_cache", return_value=False),
            patch("backend.core.cache._uses_redis_cache", return_value=True),
        ):
            mock_settings.CACHE_ENABLED = True
            value = await cache_get_json("ga:fi-redis")
        self.assertIsNone(value)

    async def test_cache_miss_storm_skips_backend(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value='{"ok":true}')
        with (
            injecting(FaultKind.REDIS_CACHE_MISS_STORM),
            patch("backend.core.cache.redis_client", client),
            patch("backend.core.cache._uses_local_cache", return_value=False),
            patch("backend.core.cache._uses_redis_cache", return_value=True),
            patch("backend.core.cache.settings") as mock_settings,
        ):
            mock_settings.CACHE_ENABLED = True
            self.assertTrue(should_force_cache_miss())
            value = await cache_get_json("ga:fi-miss-storm")
        self.assertIsNone(value)
        client.get.assert_not_awaited()


class PostgresReadinessInjectionTest(unittest.TestCase):
    def test_readiness_marks_db_unavailable(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _readiness_response(
                {"db": "error", "redis": "ok", "queue": "ok"},
                required_checks={"db", "redis", "queue"},
            )
        detail = context.exception.detail
        self.assertEqual(detail["status"], "degraded")
        self.assertEqual(detail["dependency_states"]["db"], "unavailable")
        assert_no_secrets(detail)


class StorageInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_upload_failure_is_unavailable(self) -> None:
        storage = ObjectStorage()
        with (
            injecting(FaultKind.STORAGE_UPLOAD_FAILURE),
            patch.object(ObjectStorage, "is_configured", True),
            patch("backend.core.storage.settings") as mock_settings,
        ):
            mock_settings.STORAGE_BUCKET = "bucket"
            with self.assertRaises(InjectedFailure):
                await storage.upload_bytes(
                    object_key="a.bin",
                    body=b"x",
                    content_type="application/octet-stream",
                )
        self.assertEqual(
            operational_state_for_fault(FaultKind.STORAGE_UPLOAD_FAILURE), "unavailable"
        )


class AiProviderInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_exhausts_retries_with_correlation_safe_error(self) -> None:
        client = AsyncMock()
        client.post = AsyncMock(side_effect=AssertionError("should not call provider"))
        with (
            injecting(FaultKind.AI_TIMEOUT),
            patch("backend.modules.ai.provider_retry.settings") as mock_settings,
        ):
            mock_settings.AI_PROVIDER_MAX_RETRIES = 1
            mock_settings.AI_REQUEST_TIMEOUT_SECONDS = 5
            mock_settings.AI_MAX_CONCURRENT_PROVIDER_CALLS = 2
            mock_settings.AI_PROVIDER_BACKOFF_MAX_SECONDS = 0.01
            mock_settings.AI_PROVIDER_BACKOFF_JITTER_SECONDS = 0.0
            with self.assertRaises(Exception) as context:
                await post_with_retry(
                    client,
                    "https://example.invalid/v1",
                    provider_key="openai",
                    operation="embed",
                    json={},
                )
        self.assertTrue(
            "timeout" in str(context.exception).lower()
            or "timed out" in str(context.exception).lower()
        )
        assert_no_secrets(str(context.exception))
        client.post.assert_not_awaited()

    async def test_rate_limit_returns_retryable_response(self) -> None:
        client = AsyncMock()
        with (
            injecting(FaultKind.AI_RATE_LIMIT),
            patch("backend.modules.ai.provider_retry.settings") as mock_settings,
        ):
            mock_settings.AI_PROVIDER_MAX_RETRIES = 0
            mock_settings.AI_REQUEST_TIMEOUT_SECONDS = 5
            mock_settings.AI_MAX_CONCURRENT_PROVIDER_CALLS = 2
            mock_settings.AI_PROVIDER_BACKOFF_MAX_SECONDS = 0.01
            mock_settings.AI_PROVIDER_BACKOFF_JITTER_SECONDS = 0.0
            response = await post_with_retry(
                client,
                "https://example.invalid/v1",
                provider_key="openai",
                operation="chat",
                idempotent=False,
                json={},
            )
        self.assertEqual(response.status_code, 429)
        client.post.assert_not_awaited()


class CeleryInjectionTest(unittest.TestCase):
    def test_worker_failure_raises(self) -> None:
        task = MagicMock()
        with injecting(FaultKind.CELERY_WORKER_FAILURE):
            with self.assertRaises(InjectedFailure):
                dispatch_background_sync_job(
                    target=lambda: None,
                    kwargs={},
                    celery_task=task,
                    celery_kwargs={},
                    queue="default",
                    job_name="demo",
                )
        task.apply_async.assert_not_called()

    def test_duplicate_execution_publishes_twice(self) -> None:
        task = MagicMock()
        with (
            injecting(FaultKind.CELERY_DUPLICATE),
            patch("backend.workers.async_dispatch.settings") as mock_settings,
        ):
            mock_settings.CELERY_TASK_ALWAYS_EAGER = False
            mock_settings.is_production = False
            dispatch_background_sync_job(
                target=lambda: None,
                kwargs={},
                celery_task=task,
                celery_kwargs={"job_id": "1"},
                queue="default",
                job_name="demo",
            )
        self.assertEqual(task.apply_async.call_count, 2)


class EmailInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_smtp_unavailable(self) -> None:
        with (
            injecting(FaultKind.EMAIL_SMTP_UNAVAILABLE),
            patch("backend.workers.email.settings") as mock_settings,
        ):
            mock_settings.SMTP_HOST = "smtp.example"
            with self.assertRaises(InjectedFailure):
                await _deliver_email(
                    to="a@example.com",
                    subject="s",
                    html_body="<p>x</p>",
                    text_body=None,
                    message_id="<id@example>",
                )


class RagInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_vector_unavailable_readiness(self) -> None:
        from backend.lib.vector_search import pgvector_readiness, reset_pgvector_readiness_cache

        reset_pgvector_readiness_cache()
        db = MagicMock()
        db.bind = MagicMock()
        db.bind.url = "postgresql+asyncpg://injected"
        with injecting(FaultKind.RAG_VECTOR_UNAVAILABLE):
            result = await pgvector_readiness(db)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "injected_unavailable")

    async def test_embedding_failure(self) -> None:
        from backend.modules.rag.application.embedding_service import EmbeddingService

        service = EmbeddingService()
        with injecting(FaultKind.RAG_EMBEDDING_FAILURE):
            with self.assertRaises(InjectedFailure):
                await service.embed_texts(["hello"])


class SerializationAndSecretsTest(unittest.TestCase):
    def test_injected_errors_do_not_embed_secrets(self) -> None:
        with injecting(FaultKind.POSTGRES_CONNECTION):
            with self.assertRaises(InjectedFailure) as context:
                maybe_inject(FaultKind.POSTGRES_CONNECTION)
        assert_no_secrets(str(context.exception))
        assert_no_secrets({"kind": FaultKind.REDIS_TIMEOUT.value, "detail": "timeout"})


class IdempotencyUnderDuplicateDispatchTest(unittest.TestCase):
    def test_duplicate_fault_is_degraded_not_silent_success(self) -> None:
        self.assertEqual(
            operational_state_for_fault(FaultKind.CELERY_DUPLICATE), "degraded"
        )


if __name__ == "__main__":
    unittest.main()
