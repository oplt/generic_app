"""add project organization tenancy

Revision ID: d3e8f1a2b509
Revises: a8c3f1e7b204
Create Date: 2026-09-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3e8f1a2b509"
down_revision: str | Sequence[str] | None = "a8c3f1e7b204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREFLIGHT_ERROR = (
    "Project tenancy preflight failed. "
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
    op.add_column(
        "projects",
        sa.Column("organization_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        op.f("ix_projects_organization_id"),
        "projects",
        ["organization_id"],
        unique=False,
    )

    # Backfill from the project owner's earliest membership.
    op.execute(
        """
        UPDATE projects AS project
        SET organization_id = membership.organization_id
        FROM (
            SELECT DISTINCT ON (user_id)
                user_id,
                organization_id
            FROM organization_memberships
            ORDER BY user_id, created_at ASC, id ASC
        ) AS membership
        WHERE project.owner_id = membership.user_id
          AND project.organization_id IS NULL
        """
    )

    # Owners without any membership get a personal organization.
    op.execute(
        """
        DO $$
        DECLARE
            row RECORD;
            new_org_id TEXT;
            new_membership_id TEXT;
            org_name TEXT;
        BEGIN
            FOR row IN
                SELECT project.id AS project_id,
                       project.owner_id,
                       users.email,
                       users.full_name
                FROM projects AS project
                JOIN users ON users.id = project.owner_id
                WHERE project.organization_id IS NULL
            LOOP
                new_org_id := gen_random_uuid()::text;
                new_membership_id := gen_random_uuid()::text;
                org_name := left(
                    coalesce(nullif(btrim(row.full_name), ''), row.email),
                    255
                );
                INSERT INTO organizations (id, name, created_at)
                VALUES (new_org_id, org_name, NOW());
                INSERT INTO organization_memberships (
                    id, organization_id, user_id, role, created_at
                )
                VALUES (
                    new_membership_id, new_org_id, row.owner_id, 'owner', NOW()
                );
                UPDATE projects
                SET organization_id = new_org_id
                WHERE id = row.project_id;
            END LOOP;
        END
        $$
        """
    )

    _assert_no_rows(
        "projects.organization_id still null",
        "SELECT 1 FROM projects WHERE organization_id IS NULL",
    )

    # Align scoped rows that already reference a project.
    for table in ("rag_documents", "rag_chunks", "rag_queries", "chat_conversations"):
        op.execute(
            f"""
            UPDATE {table} AS scoped
            SET organization_id = project.organization_id
            FROM projects AS project
            WHERE scoped.project_id = project.id
              AND scoped.organization_id IS DISTINCT FROM project.organization_id
            """
        )

    op.alter_column("projects", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_projects_organization_id_organizations",
        "projects",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        CREATE FUNCTION enforce_project_organization_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.project_id IS NULL THEN
                RETURN NEW;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM projects AS project
                WHERE project.id = NEW.project_id
                  AND project.organization_id IS NOT DISTINCT FROM NEW.organization_id
            ) THEN
                RAISE EXCEPTION
                    'organization_id must match projects.organization_id for project_id'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_project_organization_scope';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    for table in ("rag_documents", "rag_chunks", "rag_queries", "chat_conversations"):
        op.execute(
            f"""
            CREATE CONSTRAINT TRIGGER ck_{table}_project_organization_scope
            AFTER INSERT OR UPDATE OF project_id, organization_id ON {table}
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION enforce_project_organization_scope()
            """
        )


def downgrade() -> None:
    for table in ("rag_documents", "rag_chunks", "rag_queries", "chat_conversations"):
        op.execute(
            f"DROP TRIGGER IF EXISTS ck_{table}_project_organization_scope ON {table}"
        )
    op.execute("DROP FUNCTION IF EXISTS enforce_project_organization_scope()")
    op.drop_constraint(
        "fk_projects_organization_id_organizations",
        "projects",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_projects_organization_id"), table_name="projects")
    op.drop_column("projects", "organization_id")
