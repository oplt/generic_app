"""Phase 7 cross-feature acceptance: blue/green RAG, injection, isolation."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.lib.failure_injection import FaultKind, injecting
from backend.lib.failure_injection.runtime import InjectedFailure
from backend.modules.rag.application.embedding_service import EmbeddingService
from backend.modules.rag.application.index_version_service import IndexVersionService
from backend.modules.rag.infrastructure.chunk_search import _scope_filters
from backend.modules.rag.infrastructure.models import RAG_VECTOR_DIMENSIONS


class RagBlueGreenAcceptanceTest(unittest.IsolatedAsyncioTestCase):
    """Prompt 7.3 checklist at the service boundary (no invented latency targets)."""

    def _config(self) -> SimpleNamespace:
        return SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            document_aware_chunking=False,
            parent_child_chunking=False,
        )

    async def test_validate_activate_query_scope_rollback(self) -> None:
        db = AsyncMock()
        db.flush = AsyncMock()
        service = IndexVersionService(db, config=self._config())

        building = SimpleNamespace(
            id="v-build",
            key="idx-candidate",
            status="building",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            activated_at=None,
            retired_at=None,
            validated_at=None,
        )
        service._lock_version = AsyncMock(return_value=building)  # type: ignore[method-assign]
        with self.assertRaises(HTTPException) as blocked_building:
            await service.activate("v-build")
        self.assertEqual(blocked_building.exception.status_code, 422)

        candidate = SimpleNamespace(
            id="v-build",
            key="idx-candidate",
            status="validated",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            activated_at=None,
            retired_at=None,
            validated_at="ts",
        )
        service._lock_version = AsyncMock(return_value=candidate)  # type: ignore[method-assign]
        service.promotion_readiness = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "ready_for_activation": False,
                "documents_incomplete": 2,
                "coverage": 0.5,
            }
        )
        with self.assertRaises(HTTPException) as blocked_ready:
            await service.activate("v-build")
        self.assertEqual(blocked_ready.exception.status_code, 422)

        service.promotion_readiness = AsyncMock(  # type: ignore[method-assign]
            return_value={"ready_for_activation": True, "documents_incomplete": 0}
        )
        service._retire_other_active = AsyncMock()  # type: ignore[method-assign]
        with patch(
            "backend.modules.rag.application.index_version_service.bump_corpus_generation",
            new=AsyncMock(),
        ):
            active = await service.activate("v-build")
        self.assertEqual(active.status, "active")

        filters, params = _scope_filters(
            user_id="tenant-a",
            project_id="proj-1",
            document_ids=None,
            source_type=None,
            organization_id="org-1",
            index_version_id=active.id,
        )
        joined = " AND ".join(filters)
        self.assertIn("user_id", joined)
        self.assertIn("organization_id", joined)
        self.assertIn("index_version_id", joined)
        self.assertEqual(params["user_id"], "tenant-a")
        self.assertEqual(params["organization_id"], "org-1")
        self.assertEqual(params["index_version_id"], active.id)

        retired = SimpleNamespace(
            id="v-old",
            key="idx-old",
            status="retired",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            activated_at=None,
            retired_at="ts",
            validated_at="ts",
        )
        service._lock_version = AsyncMock(return_value=retired)  # type: ignore[method-assign]
        service._count_chunks_for_version = AsyncMock(return_value=12)  # type: ignore[method-assign]
        service._retire_other_active = AsyncMock()  # type: ignore[method-assign]
        with patch(
            "backend.modules.rag.application.index_version_service.bump_corpus_generation",
            new=AsyncMock(),
        ):
            restored = await service.rollback("v-old")
        self.assertEqual(restored.status, "active")
        service._retire_other_active.assert_awaited()


class EmbeddingPartialFailureAcceptanceTest(unittest.IsolatedAsyncioTestCase):
    async def test_partial_embedding_fault_fails_closed(self) -> None:
        service = EmbeddingService()
        with (
            injecting(FaultKind.AI_EMBEDDING_PARTIAL),
            self.assertRaises(InjectedFailure),
        ):
            await service.embed_texts(["alpha", "beta"])


class TenantIsolationFilterAcceptanceTest(unittest.TestCase):
    def test_retrieval_filters_always_include_tenant_and_version(self) -> None:
        filters, params = _scope_filters(
            user_id="u-1",
            project_id=None,
            document_ids=["d1", "d2"],
            source_type="upload",
            organization_id="org-9",
            index_version_id="idx-active",
        )
        blob = " ".join(filters)
        self.assertIn("user_id", blob)
        self.assertIn("organization_id", blob)
        self.assertIn("index_version_id", blob)
        self.assertIn("document_id", blob)
        self.assertEqual(params["organization_id"], "org-9")
        self.assertEqual(params["index_version_id"], "idx-active")


if __name__ == "__main__":
    unittest.main()
