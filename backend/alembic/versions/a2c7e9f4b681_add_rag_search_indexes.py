"""add RAG search and cursor pagination indexes

Revision ID: a2c7e9f4b681
Revises: d1f9384a80d7
Create Date: 2026-09-14

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a2c7e9f4b681"
down_revision: str | Sequence[str] | None = "d1f9384a80d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_rag_chunks_embedding_hnsw",
        "rag_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_rag_chunks_user_project_document",
        "rag_chunks",
        ["user_id", "project_id", "document_id"],
        unique=False,
    )
    op.create_index(
        "ix_rag_documents_user_project_status",
        "rag_documents",
        ["user_id", "project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_rag_chunks_document_created_id",
        "rag_chunks",
        ["document_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_rag_documents_user_created_id",
        "rag_documents",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_rag_queries_user_created_id",
        "rag_queries",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_runs_user_created_id",
        "ai_runs",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_user_created_id",
        "notifications",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_audit_user_created_id",
        "memory_audit_logs",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_project_tasks_project_created_id",
        "project_tasks",
        ["project_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_tasks_project_created_id", table_name="project_tasks")
    op.drop_index("ix_memory_audit_user_created_id", table_name="memory_audit_logs")
    op.drop_index("ix_notifications_user_created_id", table_name="notifications")
    op.drop_index("ix_ai_runs_user_created_id", table_name="ai_runs")
    op.drop_index("ix_rag_queries_user_created_id", table_name="rag_queries")
    op.drop_index("ix_rag_documents_user_created_id", table_name="rag_documents")
    op.drop_index("ix_rag_chunks_document_created_id", table_name="rag_chunks")
    op.drop_index("ix_rag_documents_user_project_status", table_name="rag_documents")
    op.drop_index("ix_rag_chunks_user_project_document", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_embedding_hnsw", table_name="rag_chunks")
