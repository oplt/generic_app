from __future__ import annotations

import unittest
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.tests.integration_support import integration_enabled, rag_integration_ready

RAG_VECTOR_DIMENSIONS = 1536

BASE_MIGRATION = (
    Path(__file__).parents[3]
    / "alembic"
    / "versions"
    / "d1f9384a80d7_generate_tables.py"
)
MIGRATION = BASE_MIGRATION.with_name("a2c7e9f4b681_add_rag_search_indexes.py")
TENANT_MIGRATION = BASE_MIGRATION.with_name(
    "b4e2d8a61f03_enforce_tenant_scope_integrity.py"
)
DEDUP_MIGRATION = BASE_MIGRATION.with_name(
    "c7f1a9d2e804_serialize_rag_document_deduplication.py"
)
FTS_MIGRATION = BASE_MIGRATION.with_name("a8c3f1e7b204_add_rag_lexical_fts_index.py")
FTS_TSV_MIGRATION = BASE_MIGRATION.with_name(
    "j0f7b5d1e148_add_rag_chunk_content_tsv.py"
)


def test_pgvector_migration_declares_schema_contract() -> None:
    base_source = BASE_MIGRATION.read_text(encoding="utf-8")
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "a2c7e9f4b681"' in source
    assert 'down_revision: str | Sequence[str] | None = "d1f9384a80d7"' in source
    assert 'CREATE EXTENSION IF NOT EXISTS vector' in base_source
    assert f"VECTOR({RAG_VECTOR_DIMENSIONS})" in base_source
    assert "ix_rag_chunks_embedding_hnsw" in source
    assert "vector_cosine_ops" in source
    assert "ix_rag_chunks_user_project_document" in source
    assert "ix_rag_documents_user_project_status" in source


def test_tenant_integrity_migration_is_head_and_declares_constraints() -> None:
    source = TENANT_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "b4e2d8a61f03"' in source
    assert 'down_revision: str | Sequence[str] | None = "a2c7e9f4b681"' in source
    for constraint in (
        "fk_rag_documents_organization_id_organizations",
        "fk_rag_documents_project_id_projects",
        "fk_rag_chunks_organization_id_organizations",
        "fk_rag_chunks_project_id_projects",
        "fk_rag_queries_organization_id_organizations",
        "fk_rag_queries_project_id_projects",
        "fk_rag_ingestion_jobs_project_id_projects",
        "fk_chat_conversations_organization_id_organizations",
        "ck_rag_chunks_document_scope",
        "ck_rag_ingestion_jobs_document_scope",
        "ck_rag_documents_child_scope",
    ):
        assert constraint in source


def test_tenant_scope_models_declare_reference_delete_policies() -> None:
    from backend.modules.chat.models import ChatConversation
    from backend.modules.rag.infrastructure.models import (
        RagChunk,
        RagDocument,
        RagIngestionJob,
        RagQueryRecord,
    )

    expectations = (
        (RagDocument.organization_id, "organizations.id", "RESTRICT"),
        (RagDocument.project_id, "projects.id", "SET NULL"),
        (RagChunk.organization_id, "organizations.id", "RESTRICT"),
        (RagChunk.project_id, "projects.id", "SET NULL"),
        (RagQueryRecord.organization_id, "organizations.id", "RESTRICT"),
        (RagQueryRecord.project_id, "projects.id", "SET NULL"),
        (RagIngestionJob.project_id, "projects.id", "SET NULL"),
        (ChatConversation.organization_id, "organizations.id", "RESTRICT"),
    )
    for attribute, target, ondelete in expectations:
        foreign_key = next(iter(attribute.property.columns[0].foreign_keys))
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == ondelete


def test_rag_document_deduplication_declares_null_safe_active_scope_index() -> None:
    source = DEDUP_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "c7f1a9d2e804"' in source
    assert 'down_revision: str | Sequence[str] | None = "b4e2d8a61f03"' in source
    assert "uq_rag_documents_active_scope_fingerprint" in source
    assert "COALESCE(organization_id, '')" in source
    assert "COALESCE(project_id, '')" in source
    assert "deleted_at IS NULL AND content_fingerprint IS NOT NULL" in source


def test_lexical_fts_migration_declares_gin_content_index() -> None:
    source = FTS_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "a8c3f1e7b204"' in source
    assert 'down_revision: str | Sequence[str] | None = "f2a6d8c9e104"' in source
    assert "ix_rag_chunks_content_fts" in source
    assert "gin (to_tsvector('simple', coalesce(content, '')))" in source


def test_lexical_tsv_migration_stores_generated_column() -> None:
    source = FTS_TSV_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "j0f7b5d1e148"' in source
    assert 'down_revision: str | Sequence[str] | None = "i9e6a4c0d037"' in source
    assert "content_tsv" in source
    assert "GENERATED ALWAYS AS" in source
    assert "ix_rag_chunks_content_tsv" in source
    assert "DROP INDEX IF EXISTS ix_rag_chunks_content_fts" in source


def test_rag_chunk_maps_fixed_dimension_vector_column() -> None:
    pytest.importorskip("pgvector")
    from backend.modules.rag.infrastructure.models import RagChunk

    column = RagChunk.__table__.c.embedding
    assert column.nullable is True
    assert column.type.dim == RAG_VECTOR_DIMENSIONS


def test_cursor_pagination_migration_declares_hot_list_indexes() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

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
