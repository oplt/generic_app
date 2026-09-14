"""add GIN FTS index for independent lexical RAG retrieval

Revision ID: a8c3f1e7b204
Revises: f2a6d8c9e104
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a8c3f1e7b204"
down_revision: str | Sequence[str] | None = "f2a6d8c9e104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_rag_chunks_content_fts
        ON rag_chunks
        USING gin (to_tsvector('simple', coalesce(content, '')))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_content_fts")
