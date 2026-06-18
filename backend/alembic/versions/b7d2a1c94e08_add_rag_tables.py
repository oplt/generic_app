"""add rag tables

Revision ID: b7d2a1c94e08
Revises: a8c4e2f91b03
Create Date: 2026-06-16 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2a1c94e08"
down_revision: str | Sequence[str] | None = "a8c4e2f91b03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rag_documents_user_id"), "rag_documents", ["user_id"])
    op.create_index(op.f("ix_rag_documents_project_id"), "rag_documents", ["project_id"])
    op.create_index(op.f("ix_rag_documents_status"), "rag_documents", ["status"])

    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("vector_external_id", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rag_chunks_document_id"), "rag_chunks", ["document_id"])
    op.create_index(op.f("ix_rag_chunks_user_id"), "rag_chunks", ["user_id"])
    op.create_index(op.f("ix_rag_chunks_project_id"), "rag_chunks", ["project_id"])

    op.create_table(
        "rag_queries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("retrieved_chunk_ids_json", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rag_queries_user_id"), "rag_queries", ["user_id"])
    op.create_index(op.f("ix_rag_queries_project_id"), "rag_queries", ["project_id"])
    op.create_index(op.f("ix_rag_queries_created_at"), "rag_queries", ["created_at"])

    op.create_table(
        "rag_ingestion_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rag_ingestion_jobs_document_id"), "rag_ingestion_jobs", ["document_id"]
    )
    op.create_index(op.f("ix_rag_ingestion_jobs_status"), "rag_ingestion_jobs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_rag_ingestion_jobs_status"), table_name="rag_ingestion_jobs")
    op.drop_index(op.f("ix_rag_ingestion_jobs_document_id"), table_name="rag_ingestion_jobs")
    op.drop_table("rag_ingestion_jobs")

    op.drop_index(op.f("ix_rag_queries_created_at"), table_name="rag_queries")
    op.drop_index(op.f("ix_rag_queries_project_id"), table_name="rag_queries")
    op.drop_index(op.f("ix_rag_queries_user_id"), table_name="rag_queries")
    op.drop_table("rag_queries")

    op.drop_index(op.f("ix_rag_chunks_project_id"), table_name="rag_chunks")
    op.drop_index(op.f("ix_rag_chunks_user_id"), table_name="rag_chunks")
    op.drop_index(op.f("ix_rag_chunks_document_id"), table_name="rag_chunks")
    op.drop_table("rag_chunks")

    op.drop_index(op.f("ix_rag_documents_status"), table_name="rag_documents")
    op.drop_index(op.f("ix_rag_documents_project_id"), table_name="rag_documents")
    op.drop_index(op.f("ix_rag_documents_user_id"), table_name="rag_documents")
    op.drop_table("rag_documents")
