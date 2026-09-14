"""serialize active RAG document deduplication

Revision ID: c7f1a9d2e804
Revises: b4e2d8a61f03
Create Date: 2026-09-14

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7f1a9d2e804"
down_revision: str | Sequence[str] | None = "b4e2d8a61f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_rag_documents_active_scope_fingerprint"


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM rag_documents
                WHERE deleted_at IS NULL
                  AND content_fingerprint IS NOT NULL
                GROUP BY user_id, organization_id, project_id, content_fingerprint
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'RAG deduplication preflight failed: duplicate active document fingerprints; '
                    'repair duplicates before retrying migration';
            END IF;
        END
        $$
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON rag_documents (
            user_id,
            COALESCE(organization_id, ''),
            COALESCE(project_id, ''),
            content_fingerprint
        )
        WHERE deleted_at IS NULL AND content_fingerprint IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="rag_documents")
