"""store generated tsvector for RAG lexical lane

Revision ID: j0f7b5d1e148
Revises: i9e6a4c0d037
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "j0f7b5d1e148"
down_revision: str | Sequence[str] | None = "i9e6a4c0d037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE rag_chunks
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_content_fts")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_rag_chunks_content_tsv
        ON rag_chunks
        USING gin (content_tsv)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_content_tsv")
    op.execute("ALTER TABLE rag_chunks DROP COLUMN IF EXISTS content_tsv")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_rag_chunks_content_fts
        ON rag_chunks
        USING gin (to_tsvector('simple', coalesce(content, '')))
        """
    )
