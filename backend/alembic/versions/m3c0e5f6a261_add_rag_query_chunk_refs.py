"""Add rag_query_chunk_refs and backfill from retrieved_chunk_ids_json.

Revision ID: m3c0e5f6a261
Revises: l2b9d4e5f150
Create Date: 2026-09-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m3c0e5f6a261"
down_revision: str | Sequence[str] | None = "l2b9d4e5f150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_query_chunk_refs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("query_id", sa.String(), nullable=False),
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("retrieval_lane", sa.String(length=32), nullable=True),
        sa.Column("raw_score", sa.Float(), nullable=True),
        sa.Column("fused_score", sa.Float(), nullable=True),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["rag_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["rag_queries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "query_id", "chunk_id", name="uq_rag_query_chunk_refs_query_chunk"
        ),
    )
    op.create_index(
        "ix_rag_query_chunk_refs_query_id",
        "rag_query_chunk_refs",
        ["query_id"],
        unique=False,
    )
    op.create_index(
        "ix_rag_query_chunk_refs_chunk_id",
        "rag_query_chunk_refs",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        "ix_rag_query_chunk_refs_query_rank",
        "rag_query_chunk_refs",
        ["query_id", "rank"],
        unique=False,
    )

    # Backfill from immutable JSON snapshots where chunks still exist.
    # Invalid JSON / orphan chunk ids are skipped.
    op.execute(
        sa.text(
            """
            INSERT INTO rag_query_chunk_refs (
                id, query_id, chunk_id, rank, created_at
            )
            SELECT
                md5(q.id || ':' || chunk.chunk_id || ':' || chunk.ord::text),
                q.id,
                chunk.chunk_id,
                chunk.ord::integer,
                COALESCE(q.created_at, NOW())
            FROM rag_queries q
            CROSS JOIN LATERAL (
                SELECT
                    elem AS chunk_id,
                    ordinality AS ord
                FROM jsonb_array_elements_text(
                    CASE
                        WHEN q.retrieved_chunk_ids_json IS NULL
                            OR btrim(q.retrieved_chunk_ids_json) = ''
                            THEN '[]'::jsonb
                        WHEN q.retrieved_chunk_ids_json::text LIKE '[%'
                            THEN q.retrieved_chunk_ids_json::jsonb
                        ELSE '[]'::jsonb
                    END
                ) WITH ORDINALITY AS t(elem, ordinality)
            ) AS chunk
            WHERE EXISTS (
                SELECT 1 FROM rag_chunks c WHERE c.id = chunk.chunk_id
            )
            ON CONFLICT (query_id, chunk_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_rag_query_chunk_refs_query_rank", table_name="rag_query_chunk_refs")
    op.drop_index("ix_rag_query_chunk_refs_chunk_id", table_name="rag_query_chunk_refs")
    op.drop_index("ix_rag_query_chunk_refs_query_id", table_name="rag_query_chunk_refs")
    op.drop_table("rag_query_chunk_refs")
