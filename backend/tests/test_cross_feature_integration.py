"""Cross-feature integration checks for Phase 17 wiring."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.modules.diagnostics.schemas import DiagnosticsSection
from backend.modules.diagnostics.service import DiagnosticsService
from backend.modules.manifests import REGISTERED_MANIFESTS, validate_registry
from backend.modules.platform.profiles import CAPABILITY_PROFILES, resolve_capability_profile
from backend.modules.policy import catalog
from backend.lib.failure_injection import FaultKind, injecting


class ManifestProfileRbacIntegrationTest(unittest.TestCase):
    def test_registry_and_profiles_agree_on_permissions(self) -> None:
        validate_registry()
        known_permissions = set(catalog.ALL_PERMISSIONS)
        for manifest in REGISTERED_MANIFESTS:
            unknown = set(manifest.required_permissions) - known_permissions
            self.assertFalse(
                unknown,
                f"{manifest.key} declares unknown permissions: {unknown}",
            )
        for key in CAPABILITY_PROFILES:
            resolution = resolve_capability_profile(key)
            self.assertTrue(resolution.active_modules)
            unknown = set(resolution.required_permissions) - known_permissions
            self.assertFalse(unknown, f"profile {key} has unknown permissions: {unknown}")


class JobsDiagnosticsRagManifestTest(unittest.TestCase):
    def test_jobs_diagnostics_and_rag_are_registered(self) -> None:
        keys = {manifest.key for manifest in REGISTERED_MANIFESTS}
        for required in ("jobs", "diagnostics", "developer_diagnostics", "rag", "policy"):
            self.assertIn(required, keys)
        jobs = next(item for item in REGISTERED_MANIFESTS if item.key == "jobs")
        self.assertIn("jobs.read", jobs.required_permissions)
        diagnostics = next(item for item in REGISTERED_MANIFESTS if item.key == "diagnostics")
        self.assertIn("diagnostics.read", diagnostics.required_permissions)


class DiagnosticsObservabilityInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_observability_hints_include_links_and_injection(self) -> None:
        service = DiagnosticsService(MagicMock())

        async def _healthy() -> DiagnosticsSection:
            return DiagnosticsSection(state="healthy", detail="ok", metrics={})

        service._application = _healthy  # type: ignore[method-assign]
        service._postgresql = _healthy  # type: ignore[method-assign]
        service._redis = _healthy  # type: ignore[method-assign]
        service._celery = _healthy  # type: ignore[method-assign]
        service._storage = _healthy  # type: ignore[method-assign]
        service._ai_providers = AsyncMock(return_value=[])  # type: ignore[method-assign]
        service._rag = _healthy  # type: ignore[method-assign]

        with injecting(FaultKind.REDIS_CACHE_MISS_STORM):
            report = await service.collect()

        hints = report.observability_hints
        self.assertIn("grafana_base_url", hints)
        self.assertIn("tempo_explore_url", hints)
        self.assertEqual(hints["observability_page"], "/observability")
        self.assertIn("redis.cache_miss_storm", hints["failure_injection"]["active_faults"])
        self.assertNotEqual(report.overall_state, "healthy")


class EvaluationIndexVersionIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_dataset_records_index_version(self) -> None:
        from backend.modules.rag.application.evaluation_service import RagEvaluationService

        db = MagicMock()
        db.flush = AsyncMock()
        service = RagEvaluationService(db)
        dataset = SimpleNamespace(id="ds-1")
        case = SimpleNamespace(
            id="case-1",
            question="q",
            expected_chunk_ids_json=["c1"],
            judgments_json={},
        )
        run = SimpleNamespace(
            id="run-1",
            configuration_json={},
            status="running",
            metrics_json={},
            latency_json={},
            comparison_json=None,
            error_message=None,
            completed_at=None,
        )

        service.get_dataset = AsyncMock(return_value=dataset)  # type: ignore[method-assign]
        service.repo.list_cases = AsyncMock(return_value=[case])
        service.repo.create_run = AsyncMock(return_value=run)
        service.repo.create_run_item = AsyncMock()
        service.repo.save_run = AsyncMock(return_value=run)
        service._retrieve_detailed = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "candidates": [{"chunk_id": "c1", "content": "hello"}],
                "context_chunks": [{"content": "hello"}],
                "latencies_ms": {
                    "embedding": 1,
                    "vector": 1,
                    "lexical": 0,
                    "fusion": 0,
                    "rerank": 0,
                    "context": 0,
                    "total": 2,
                },
            }
        )

        active = SimpleNamespace(
            key="idx-test",
            parser_version="parser-v1",
            chunker_version="chunker-v1",
            embedding_schema_version="embed-v1",
            embedding_provider="local",
            embedding_model="local",
            embedding_dimensions=1536,
        )
        with patch(
            "backend.modules.rag.application.index_version_service.IndexVersionService.ensure_active_version",
            AsyncMock(return_value=active),
        ):
            await service.run_dataset(
                "ds-1",
                user_id="u1",
                organization_id=None,
                strategy="hybrid_rrf",
                top_k=5,
            )

        created_config = service.repo.create_run.await_args.kwargs["configuration_json"]
        self.assertEqual(created_config["strategy"], "hybrid_rrf")
        self.assertEqual(created_config["index_version"], "idx-test")
        self.assertEqual(created_config["pipeline"]["embedding_provider"], "local")
