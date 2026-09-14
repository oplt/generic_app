"""Add chunk index_version_id, one-active invariant, and side-by-side indexes.

Revision ID: n4d1f6a7b372
Revises: m3c0e5f6a261
Create Date: 2026-09-14 21:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "n4d1f6a7b372"
down_revision: str | Sequence[str] | None = "m3c0e5f6a261"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rag_chunks",
        sa.Column("index_version_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_rag_chunks_index_version_id",
        "rag_chunks",
        "rag_index_versions",
        ["index_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_rag_chunks_index_version_id",
        "rag_chunks",
        ["index_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_rag_chunks_document_index_version",
        "rag_chunks",
        ["document_id", "index_version_id"],
        unique=False,
    )
    op.create_index(
        "uq_rag_chunks_document_version_chunk_index",
        "rag_chunks",
        ["document_id", "index_version_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("index_version_id IS NOT NULL"),
    )

    # At most one active index version.
    op.create_index(
        "uq_rag_index_versions_one_active",
        "rag_index_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # Backfill chunks onto the current active version when one exists.
    op.execute(
        sa.text(
            """
            UPDATE rag_chunks AS c
            SET index_version_id = v.id
            FROM rag_index_versions AS v
            WHERE v.status = 'active'
              AND c.index_version_id IS NULL
            """
        )
    )

    # If no active version yet, attach orphan chunks to the newest version row.
    op.execute(
        sa.text(
            """
            UPDATE rag_chunks AS c
            SET index_version_id = (
                SELECT id FROM rag_index_versions ORDER BY created_at DESC LIMIT 1
            )
            WHERE c.index_version_id IS NULL
              AND EXISTS (SELECT 1 FROM rag_index_versions)
            """
        )
    )


def downgrade() -> None:
    op.drop_index("uq_rag_index_versions_one_active", table_name="rag_index_versions")
    op.drop_index(
        "uq_rag_chunks_document_version_chunk_index", table_name="rag_chunks"
    )
    op.drop_index("ix_rag_chunks_document_index_version", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_index_version_id", table_name="rag_chunks")
    op.drop_constraint("fk_rag_chunks_index_version_id", "rag_chunks", type_="foreignkey")
    op.drop_column("rag_chunks", "index_version_id")
