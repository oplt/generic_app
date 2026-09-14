"""enforce RAG and chat tenant scope integrity

Revision ID: b4e2d8a61f03
Revises: a2c7e9f4b681
Create Date: 2026-09-14

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b4e2d8a61f03"
down_revision: str | Sequence[str] | None = "a2c7e9f4b681"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREFLIGHT_ERROR = (
    "Tenant integrity preflight failed. "
    "Run docs/runbooks/tenant-integrity-migration.md before retrying."
)


def _assert_no_rows(label: str, query: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS ({query}) THEN
                RAISE EXCEPTION '{_PREFLIGHT_ERROR} Violation: {label}';
            END IF;
        END
        $$
        """
    )


def upgrade() -> None:
    reference_checks = {
        "rag_documents.organization_id": """
            SELECT 1 FROM rag_documents row
            LEFT JOIN organizations target ON target.id = row.organization_id
            WHERE row.organization_id IS NOT NULL AND target.id IS NULL
        """,
        "rag_documents.project_id": """
            SELECT 1 FROM rag_documents row
            LEFT JOIN projects target ON target.id = row.project_id
            WHERE row.project_id IS NOT NULL AND target.id IS NULL
        """,
        "rag_chunks.organization_id": """
            SELECT 1 FROM rag_chunks row
            LEFT JOIN organizations target ON target.id = row.organization_id
            WHERE row.organization_id IS NOT NULL AND target.id IS NULL
        """,
        "rag_chunks.project_id": """
            SELECT 1 FROM rag_chunks row
            LEFT JOIN projects target ON target.id = row.project_id
            WHERE row.project_id IS NOT NULL AND target.id IS NULL
        """,
        "rag_queries.organization_id": """
            SELECT 1 FROM rag_queries row
            LEFT JOIN organizations target ON target.id = row.organization_id
            WHERE row.organization_id IS NOT NULL AND target.id IS NULL
        """,
        "rag_queries.project_id": """
            SELECT 1 FROM rag_queries row
            LEFT JOIN projects target ON target.id = row.project_id
            WHERE row.project_id IS NOT NULL AND target.id IS NULL
        """,
        "rag_ingestion_jobs.project_id": """
            SELECT 1 FROM rag_ingestion_jobs row
            LEFT JOIN projects target ON target.id = row.project_id
            WHERE row.project_id IS NOT NULL AND target.id IS NULL
        """,
        "chat_conversations.organization_id": """
            SELECT 1 FROM chat_conversations row
            LEFT JOIN organizations target ON target.id = row.organization_id
            WHERE row.organization_id IS NOT NULL AND target.id IS NULL
        """,
    }
    for label, query in reference_checks.items():
        _assert_no_rows(label, query)

    _assert_no_rows(
        "rag_chunks document scope",
        """
        SELECT 1
        FROM rag_chunks chunk
        JOIN rag_documents document ON document.id = chunk.document_id
        WHERE chunk.user_id IS DISTINCT FROM document.user_id
           OR chunk.organization_id IS DISTINCT FROM document.organization_id
           OR chunk.project_id IS DISTINCT FROM document.project_id
        """,
    )
    _assert_no_rows(
        "rag_ingestion_jobs document scope",
        """
        SELECT 1
        FROM rag_ingestion_jobs job
        JOIN rag_documents document ON document.id = job.document_id
        WHERE job.user_id IS DISTINCT FROM document.user_id
           OR job.project_id IS DISTINCT FROM document.project_id
        """,
    )

    foreign_keys = (
        (
            "fk_rag_documents_organization_id_organizations",
            "rag_documents",
            "organizations",
            ["organization_id"],
            ["id"],
            "RESTRICT",
        ),
        (
            "fk_rag_documents_project_id_projects",
            "rag_documents",
            "projects",
            ["project_id"],
            ["id"],
            "SET NULL",
        ),
        (
            "fk_rag_chunks_organization_id_organizations",
            "rag_chunks",
            "organizations",
            ["organization_id"],
            ["id"],
            "RESTRICT",
        ),
        (
            "fk_rag_chunks_project_id_projects",
            "rag_chunks",
            "projects",
            ["project_id"],
            ["id"],
            "SET NULL",
        ),
        (
            "fk_rag_queries_organization_id_organizations",
            "rag_queries",
            "organizations",
            ["organization_id"],
            ["id"],
            "RESTRICT",
        ),
        (
            "fk_rag_queries_project_id_projects",
            "rag_queries",
            "projects",
            ["project_id"],
            ["id"],
            "SET NULL",
        ),
        (
            "fk_rag_ingestion_jobs_project_id_projects",
            "rag_ingestion_jobs",
            "projects",
            ["project_id"],
            ["id"],
            "SET NULL",
        ),
        (
            "fk_chat_conversations_organization_id_organizations",
            "chat_conversations",
            "organizations",
            ["organization_id"],
            ["id"],
            "RESTRICT",
        ),
    )
    for name, source, target, local_columns, remote_columns, ondelete in foreign_keys:
        op.create_foreign_key(
            name,
            source,
            target,
            local_columns,
            remote_columns,
            ondelete=ondelete,
        )

    op.execute(
        """
        CREATE FUNCTION enforce_rag_chunk_document_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM rag_documents document
                WHERE document.id = NEW.document_id
                  AND document.user_id IS NOT DISTINCT FROM NEW.user_id
                  AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND document.project_id IS NOT DISTINCT FROM NEW.project_id
            ) THEN
                RAISE EXCEPTION 'RAG chunk scope must match its document'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_rag_chunks_document_scope';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ck_rag_chunks_document_scope
        AFTER INSERT OR UPDATE ON rag_chunks
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_rag_chunk_document_scope()
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_rag_job_document_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM rag_documents document
                WHERE document.id = NEW.document_id
                  AND document.user_id IS NOT DISTINCT FROM NEW.user_id
                  AND document.project_id IS NOT DISTINCT FROM NEW.project_id
            ) THEN
                RAISE EXCEPTION 'RAG ingestion job scope must match its document'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_rag_ingestion_jobs_document_scope';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ck_rag_ingestion_jobs_document_scope
        AFTER INSERT OR UPDATE ON rag_ingestion_jobs
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_rag_job_document_scope()
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_rag_document_child_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM rag_chunks chunk
                WHERE chunk.document_id = NEW.id
                  AND (
                      chunk.user_id IS DISTINCT FROM NEW.user_id
                      OR chunk.organization_id IS DISTINCT FROM NEW.organization_id
                      OR chunk.project_id IS DISTINCT FROM NEW.project_id
                  )
            ) OR EXISTS (
                SELECT 1
                FROM rag_ingestion_jobs job
                WHERE job.document_id = NEW.id
                  AND (
                      job.user_id IS DISTINCT FROM NEW.user_id
                      OR job.project_id IS DISTINCT FROM NEW.project_id
                  )
            ) THEN
                RAISE EXCEPTION 'RAG document scope must match its chunks and jobs'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_rag_documents_child_scope';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ck_rag_documents_child_scope
        AFTER UPDATE ON rag_documents
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_rag_document_child_scope()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER ck_rag_documents_child_scope ON rag_documents")
    op.execute("DROP TRIGGER ck_rag_ingestion_jobs_document_scope ON rag_ingestion_jobs")
    op.execute("DROP TRIGGER ck_rag_chunks_document_scope ON rag_chunks")
    op.execute("DROP FUNCTION enforce_rag_document_child_scope()")
    op.execute("DROP FUNCTION enforce_rag_job_document_scope()")
    op.execute("DROP FUNCTION enforce_rag_chunk_document_scope()")

    for name, table in (
        ("fk_chat_conversations_organization_id_organizations", "chat_conversations"),
        ("fk_rag_ingestion_jobs_project_id_projects", "rag_ingestion_jobs"),
        ("fk_rag_queries_project_id_projects", "rag_queries"),
        ("fk_rag_queries_organization_id_organizations", "rag_queries"),
        ("fk_rag_chunks_project_id_projects", "rag_chunks"),
        ("fk_rag_chunks_organization_id_organizations", "rag_chunks"),
        ("fk_rag_documents_project_id_projects", "rag_documents"),
        ("fk_rag_documents_organization_id_organizations", "rag_documents"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
