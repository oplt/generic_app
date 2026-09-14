"""Tests for rag_query_chunk_refs write and relational cleanup."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.modules.rag.infrastructure.models import RagQueryChunkRef, RagQueryRecord
from backend.modules.rag.infrastructure.repositories import RagRepository


class CreateQueryRecordRefsTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_query_record_writes_refs_for_existing_chunks(self) -> None:
        db = AsyncMock()
        existing = MagicMock()
        existing.scalars.return_value.all.return_value = ["c1", "c2"]
        db.execute = AsyncMock(return_value=existing)
        db.flush = AsyncMock()
        db.add = MagicMock()

        repo = RagRepository(db)
        row = await repo.create_query_record(
            user_id="u1",
            project_id=None,
            organization_id=None,
            query="q",
            answer="a",
            retrieved_chunk_ids=["c1", "c2", "missing"],
            model_name="m",
            latency_ms=10,
            chunk_refs=[
                {"chunk_id": "c2", "rank": 2, "retrieval_lane": "vector", "raw_score": 0.9}
            ],
        )

        self.assertIsInstance(row, RagQueryRecord)
        added_refs = [
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], RagQueryChunkRef)
        ]
        self.assertEqual(len(added_refs), 2)
        self.assertEqual({ref.chunk_id for ref in added_refs}, {"c1", "c2"})
        by_id = {ref.chunk_id: ref for ref in added_refs}
        self.assertEqual(by_id["c1"].rank, 1)
        self.assertEqual(by_id["c2"].rank, 2)
        self.assertEqual(by_id["c2"].retrieval_lane, "vector")
        self.assertEqual(by_id["c2"].raw_score, 0.9)


class DeleteQueryRecordsRelationalTest(unittest.IsolatedAsyncioTestCase):
    async def test_delete_query_records_uses_refs_not_like(self) -> None:
        db = AsyncMock()
        db.execute = AsyncMock()
        repo = RagRepository(db)

        await repo.delete_query_records_for_document("doc-1")

        db.execute.assert_awaited_once()
        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
        self.assertIn("rag_query_chunk_refs", compiled)
        self.assertNotIn(" like ", compiled)
        self.assertNotIn("%.", compiled)

class CleanupTransactionOwnershipTest(unittest.IsolatedAsyncioTestCase):
    async def test_storage_delete_runs_after_db_commit(self) -> None:
        from backend.modules.rag.application.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = object.__new__(DocumentIngestionService)
        service.db = AsyncMock()
        service.db.commit = AsyncMock()
        service.repo = MagicMock()
        service.repo.delete_query_records_for_document = AsyncMock()
        service.repo.delete_ingestion_jobs_for_document = AsyncMock()
        service.repo.scrub_deleted_document = AsyncMock()
        service.vector_store = MagicMock()
        service.vector_store.delete_document = AsyncMock()
        service.storage = MagicMock()
        service.storage.delete_document = AsyncMock()

        order: list[str] = []

        async def mark_commit():
            order.append("commit")

        async def mark_storage(_path):
            order.append("storage")

        service.db.commit.side_effect = mark_commit
        service.storage.delete_document.side_effect = mark_storage

        with patch(
            "backend.modules.chat.repository.ChatRepository",
            return_value=SimpleNamespace(delete_sources_for_document=AsyncMock()),
        ):
            await service.cleanup_deleted_document(
                document_id="doc-1",
                user_id="u1",
                storage_path="rag/doc-1",
            )

        self.assertEqual(order, ["commit", "storage"])
