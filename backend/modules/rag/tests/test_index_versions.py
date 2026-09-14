"""Tests for RAG index version lifecycle helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from backend.modules.rag.application.index_version_service import IndexVersionService
from backend.modules.rag.application.pipeline_versions import (
    index_version_key,
    pipeline_version_metadata,
)
from backend.modules.rag.infrastructure.chunk_search import _scope_filters
from backend.modules.rag.infrastructure.models import RAG_VECTOR_DIMENSIONS


class PipelineIndexVersionTest(unittest.TestCase):
    def test_index_version_key_is_stable(self) -> None:
        config = SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
        )
        first = pipeline_version_metadata(config)
        second = pipeline_version_metadata(config)
        self.assertEqual(first["index_version"], second["index_version"])
        self.assertEqual(
            first["index_version"],
            index_version_key({k: first[k] for k in first if k != "index_version"}),
        )

    def test_dimension_mismatch_rejected(self) -> None:
        service = IndexVersionService(AsyncMock(), config=SimpleNamespace())
        with self.assertRaises(HTTPException) as ctx:
            service._assert_dimensions_compatible(RAG_VECTOR_DIMENSIONS + 1)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_scope_filters_include_index_version(self) -> None:
        filters, params = _scope_filters(
            user_id="u1",
            project_id=None,
            document_ids=None,
            source_type=None,
            organization_id=None,
            index_version_id="ver-1",
        )
        self.assertTrue(any("index_version_id" in clause for clause in filters))
        self.assertEqual(params["index_version_id"], "ver-1")


class IndexVersionServiceLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_activate_rejects_building(self) -> None:
        db = AsyncMock()
        config = SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
        )
        service = IndexVersionService(db, config=config)
        target = SimpleNamespace(
            id="v2",
            status="building",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            activated_at=None,
            retired_at=None,
            validated_at=None,
            key="idx-v2",
        )
        service._lock_version = AsyncMock(return_value=target)  # type: ignore[method-assign]
        with self.assertRaises(HTTPException) as ctx:
            await service.activate("v2")
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_activate_validated_retires_previous(self) -> None:
        db = AsyncMock()
        db.flush = AsyncMock()
        config = SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
        )
        service = IndexVersionService(db, config=config)
        target = SimpleNamespace(
            id="v2",
            key="idx-v2",
            status="validated",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            activated_at=None,
            retired_at=None,
            validated_at="already",
        )
        service._lock_version = AsyncMock(return_value=target)  # type: ignore[method-assign]
        service._retire_other_active = AsyncMock()  # type: ignore[method-assign]
        service.promotion_readiness = AsyncMock(  # type: ignore[method-assign]
            return_value={"ready_for_activation": True}
        )
        with patch(
            "backend.modules.rag.application.index_version_service.bump_corpus_generation",
            new=AsyncMock(),
        ):
            activated = await service.activate("v2")
        self.assertEqual(activated.status, "active")
        self.assertIsNotNone(activated.activated_at)
        service._retire_other_active.assert_awaited_once_with(except_id="v2")

    async def test_ensure_active_does_not_auto_promote_building(self) -> None:
        db = AsyncMock()
        config = SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            document_aware_chunking=False,
            parent_child_chunking=False,
        )
        service = IndexVersionService(db, config=config)
        active = SimpleNamespace(id="v1", key="idx-old", status="active")
        service.get_active_version = AsyncMock(return_value=active)  # type: ignore[method-assign]
        service.ensure_desired_building_version = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = await service.ensure_active_version()
        self.assertIs(result, active)
        service.ensure_desired_building_version.assert_awaited_once()

    async def test_ensure_desired_opens_building_on_drift(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        config = SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            document_aware_chunking=False,
            parent_child_chunking=False,
        )
        service = IndexVersionService(db, config=config)
        active = SimpleNamespace(id="v1", key="idx-different", status="active")
        service.get_active_version = AsyncMock(return_value=active)  # type: ignore[method-assign]
        service.get_by_key = AsyncMock(return_value=None)  # type: ignore[method-assign]
        building = await service.ensure_desired_building_version()
        self.assertEqual(building.status, "building")
        self.assertNotEqual(building.key, active.key)
        db.add.assert_called_once()

    async def test_rollback_requires_retired(self) -> None:
        db = AsyncMock()
        service = IndexVersionService(db, config=SimpleNamespace())
        target = SimpleNamespace(id="v1", status="validated")
        service._lock_version = AsyncMock(return_value=target)  # type: ignore[method-assign]
        with self.assertRaises(HTTPException) as ctx:
            await service.rollback("v1")
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_replace_chunks_scoped_to_version(self) -> None:
        from backend.modules.rag.infrastructure.repositories import RagRepository

        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        repo = RagRepository(db)
        document = SimpleNamespace(
            id="doc-1",
            user_id="u1",
            organization_id=None,
            project_id=None,
        )
        with patch(
            "backend.modules.rag.infrastructure.repositories.store_chunk_embeddings_batch",
            new=AsyncMock(),
        ):
            await repo.replace_chunks(
                document,
                [
                    {
                        "chunk_index": 0,
                        "content": "hello",
                        "token_count": 1,
                        "metadata": {},
                        "embedding": [0.1] * 8,
                    }
                ],
                index_version_id="ver-2",
            )
        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
        self.assertIn("index_version_id", compiled)
        added = db.add.call_args.args[0]
        self.assertEqual(added.index_version_id, "ver-2")
