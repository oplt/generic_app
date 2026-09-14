from __future__ import annotations

import unittest
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.tests.integration_support import integration_enabled, rag_integration_ready

RAG_VECTOR_DIMENSIONS = 1536

MIGRATION = (
    Path(__file__).parents[3]
    / "alembic"
    / "versions"
    / "c4e8f2a91d03_add_pgvector_schema.py"
)
CURSOR_MIGRATION = MIGRATION.with_name("d1e2f3a4b5c6_add_cursor_pagination_indexes.py")


def test_pgvector_migration_is_head_and_declares_schema_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "c4e8f2a91d03"' in source
    assert 'down_revision: str | Sequence[str] | None = "7f3c1a9d2e44"' in source
    assert 'CREATE EXTENSION IF NOT EXISTS vector' in source
    assert f"VECTOR_DIMENSIONS = {RAG_VECTOR_DIMENSIONS}" in source
    assert "Vector(VECTOR_DIMENSIONS)" in source
    assert '"ix_rag_chunks_embedding_hnsw"' in source
    assert '"vector_cosine_ops"' in source
    assert '"ix_rag_chunks_user_project_document"' in source
    assert '"ix_rag_documents_user_project_status"' in source


def test_rag_chunk_maps_fixed_dimension_vector_column() -> None:
    pytest.importorskip("pgvector")
    from backend.modules.rag.infrastructure.models import RagChunk

    column = RagChunk.__table__.c.embedding
    assert column.nullable is True
    assert column.type.dim == RAG_VECTOR_DIMENSIONS


def test_cursor_pagination_migration_declares_hot_list_indexes() -> None:
    source = CURSOR_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "d1e2f3a4b5c6"' in source
    assert 'down_revision: str | Sequence[str] | None = "c4e8f2a91d03"' in source
    for index_name in (
        "ix_rag_chunks_document_created_id",
        "ix_rag_documents_user_created_id",
        "ix_rag_queries_user_created_id",
        "ix_ai_runs_user_created_id",
        "ix_notifications_user_created_id",
        "ix_memory_audit_user_created_id",
        "ix_project_tasks_project_created_id",
    ):
        assert index_name in source


@unittest.skipUnless(
    integration_enabled() and rag_integration_ready(),
    "Set RUN_INTEGRATION_TESTS=1 with migrated PostgreSQL",
)
class PgvectorSchemaIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_live_schema_exposes_vector_column_and_hnsw_index(self) -> None:
        from backend.tests.integration_support import prepare_integration_runtime

        await prepare_integration_runtime()
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            extension = await db.scalar(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            vector_type = await db.scalar(
                text(
                    """
                    SELECT format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    WHERE c.relname = 'rag_chunks'
                      AND a.attname = 'embedding'
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                    """
                )
            )
            index_def = await db.scalar(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE tablename = 'rag_chunks'
                      AND indexname = 'ix_rag_chunks_embedding_hnsw'
                    """
                )
            )

        self.assertIsNotNone(extension)
        self.assertEqual(vector_type, f"vector({RAG_VECTOR_DIMENSIONS})")
        self.assertIsNotNone(index_def)
        self.assertIn("USING hnsw", index_def)
        self.assertIn("vector_cosine_ops", index_def)
