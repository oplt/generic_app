"""Unit tests for infrastructure diagnostics."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.modules.diagnostics.schemas import DiagnosticsSection
from backend.modules.diagnostics.service import (
    DiagnosticsService,
    _assert_no_secrets,
    _safe_host,
)


class DiagnosticsRedactionTest(unittest.TestCase):
    def test_safe_host_strips_credentials(self) -> None:
        host = _safe_host("redis://user:supersecret@redis.internal:6379/0")
        self.assertEqual(host, "redis.internal:6379")
        self.assertNotIn("supersecret", host or "")

    def test_assert_no_secrets_rejects_key_names(self) -> None:
        with self.assertRaises(AssertionError):
            _assert_no_secrets({"api_key": "x"})

    def test_assert_no_secrets_allows_safe_payload(self) -> None:
        _assert_no_secrets(
            {
                "database_host": "db.internal:5432",
                "pool": {"checked_out": 1},
                "providers": [{"key": "openai", "configured": True}],
            }
        )


class DiagnosticsAiProvidersTest(unittest.IsolatedAsyncioTestCase):
    async def test_ai_providers_do_not_call_paid_apis(self) -> None:
        service = DiagnosticsService(MagicMock())
        with (
            patch("backend.modules.diagnostics.service.settings") as mock_settings,
            patch(
                "backend.modules.diagnostics.service.AiProviderService.list_provider_descriptors",
                return_value=[
                    SimpleNamespace(
                        key="openai",
                        label="OpenAI",
                        supports_generation=True,
                        supports_embeddings=True,
                    ),
                    SimpleNamespace(
                        key="local",
                        label="Local",
                        supports_generation=True,
                        supports_embeddings=True,
                    ),
                ],
            ),
        ):
            mock_settings.OPENAI_API_KEY = "sk-test"
            mock_settings.ANTHROPIC_API_KEY = ""
            mock_settings.AI_EMBEDDING_PROVIDER = "local"
            providers = await service._ai_providers()
        openai = next(item for item in providers if item.key == "openai")
        self.assertTrue(openai.configured)
        self.assertEqual(openai.state, "healthy")
        self.assertIn("skipped", openai.detail.lower())


class DiagnosticsCollectTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_returns_sections_without_secrets(self) -> None:
        service = DiagnosticsService(MagicMock())

        async def _section(state: str = "healthy") -> DiagnosticsSection:
            return DiagnosticsSection(
                state=state,  # type: ignore[arg-type]
                detail="ok",
                metrics={"database_host": "localhost"},
            )

        service._application = AsyncMock(  # type: ignore[method-assign]
            return_value=DiagnosticsSection(
                state="healthy", detail="ok", metrics={"version": "0.1.0"}
            )
        )
        service._postgresql = _section  # type: ignore[method-assign]
        service._redis = AsyncMock(  # type: ignore[method-assign]
            return_value=DiagnosticsSection(state="healthy", detail="ok", metrics={})
        )
        service._celery = AsyncMock(  # type: ignore[method-assign]
            return_value=DiagnosticsSection(state="healthy", detail="ok", metrics={})
        )
        service._storage = AsyncMock(  # type: ignore[method-assign]
            return_value=DiagnosticsSection(state="not_required", detail="n/a", metrics={})
        )
        service._ai_providers = AsyncMock(return_value=[])  # type: ignore[method-assign]
        service._rag = AsyncMock(  # type: ignore[method-assign]
            return_value=DiagnosticsSection(state="not_required", detail="off", metrics={})
        )

        result = await service.collect()
        self.assertEqual(result.overall_state, "healthy")
        payload = result.model_dump()
        self.assertIn("postgresql", payload)
        _assert_no_secrets(payload)
        self.assertNotIn("DATABASE_URL", str(payload))


class DiagnosticsPoolMetricsTest(unittest.TestCase):
    def test_pool_metrics_expose_limits_not_dsn(self) -> None:
        service = DiagnosticsService(MagicMock())
        with patch("backend.modules.diagnostics.service.settings") as mock_settings:
            mock_settings.DB_POOL_SIZE = 10
            mock_settings.DB_MAX_OVERFLOW = 5
            mock_settings.DB_POOL_TIMEOUT_SECONDS = 30.0
            metrics = service._pool_metrics()
        self.assertEqual(metrics["configured_pool_size"], 10)
        self.assertNotIn("url", metrics)
        self.assertNotIn("dsn", metrics)
