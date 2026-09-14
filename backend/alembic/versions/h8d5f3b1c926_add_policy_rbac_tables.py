"""add policy RBAC tables and seed built-in roles

Revision ID: h8d5f3b1c926
Revises: g7c4e2a9b815
Create Date: 2026-09-14 19:00:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "h8d5f3b1c926"
down_revision: str | Sequence[str] | None = "g7c4e2a9b815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMISSIONS = {
    "project.read": "View projects and project tasks",
    "project.create": "Create projects",
    "project.update": "Update projects and tasks",
    "project.delete": "Delete projects",
    "rag.read": "Search and read RAG documents",
    "rag.manage": "Upload, delete, and manage RAG documents/jobs",
    "users.manage": "Manage organization members",
    "billing.read": "View billing and plans",
    "billing.manage": "Manage billing and plans",
    "api_keys.manage": "Manage API keys",
    "webhooks.manage": "Manage webhooks",
    "jobs.read": "View background jobs",
    "jobs.retry": "Retry failed jobs",
    "diagnostics.read": "View diagnostics and observability",
    "admin.manage": "Administer platform roles and global settings",
}

_ORG_MEMBER = (
    "project.read",
    "project.create",
    "rag.read",
    "jobs.read",
)
_ORG_ADMIN = _ORG_MEMBER + (
    "project.update",
    "project.delete",
    "rag.manage",
    "users.manage",
    "billing.read",
    "billing.manage",
    "api_keys.manage",
    "webhooks.manage",
    "jobs.retry",
    "diagnostics.read",
)
_PROJECT_EDITOR = (
    "project.read",
    "project.update",
    "rag.read",
    "rag.manage",
    "jobs.read",
    "jobs.retry",
)
_ROLES = (
    (
        "system_admin",
        "System admin",
        "system",
        "Full platform capability; maps from users.is_admin bootstrap.",
        tuple(_PERMISSIONS.keys()),
    ),
    (
        "org_admin",
        "Organization admin",
        "organization",
        "Manage projects, RAG, billing, and members inside an organization.",
        _ORG_ADMIN,
    ),
    (
        "org_member",
        "Organization member",
        "organization",
        "Create/read projects and read RAG within an organization.",
        _ORG_MEMBER,
    ),
    (
        "project_editor",
        "Project editor",
        "project",
        "Update a project and manage its RAG corpus.",
        _PROJECT_EDITOR,
    ),
)


def upgrade() -> None:
    op.create_table(
        "policy_permissions",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "policy_roles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_policy_roles_key"),
    )
    op.create_index("ix_policy_roles_key", "policy_roles", ["key"], unique=False)
    op.create_table(
        "policy_role_permissions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("permission_key", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["permission_key"], ["policy_permissions.key"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["policy_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_key", name="uq_policy_role_permission"),
    )
    op.create_index(
        "ix_policy_role_permissions_role_id",
        "policy_role_permissions",
        ["role_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_role_permissions_permission_key",
        "policy_role_permissions",
        ["permission_key"],
        unique=False,
    )
    op.create_table(
        "policy_role_assignments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["policy_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_role_assignments_user",
        "policy_role_assignments",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_role_assignments_org",
        "policy_role_assignments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_role_assignments_project",
        "policy_role_assignments",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "uq_policy_assignment_system",
        "policy_role_assignments",
        ["user_id", "role_id"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL AND project_id IS NULL"),
    )
    op.create_index(
        "uq_policy_assignment_org",
        "policy_role_assignments",
        ["user_id", "role_id", "organization_id"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL AND project_id IS NULL"),
    )
    op.create_index(
        "uq_policy_assignment_project",
        "policy_role_assignments",
        ["user_id", "role_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )

    conn = op.get_bind()
    for key, description in _PERMISSIONS.items():
        conn.execute(
            sa.text(
                "INSERT INTO policy_permissions (key, description, created_at) "
                "VALUES (:key, :description, NOW())"
            ),
            {"key": key, "description": description},
        )

    role_ids: dict[str, str] = {}
    for key, name, scope_type, description, _perms in _ROLES:
        role_id = str(uuid4())
        role_ids[key] = role_id
        conn.execute(
            sa.text(
                "INSERT INTO policy_roles "
                "(id, key, name, description, scope_type, is_system, created_at) "
                "VALUES (:id, :key, :name, :description, :scope_type, true, NOW())"
            ),
            {
                "id": role_id,
                "key": key,
                "name": name,
                "description": description,
                "scope_type": scope_type,
            },
        )

    for key, _name, _scope, _description, permissions in _ROLES:
        role_id = role_ids[key]
        for permission_key in permissions:
            conn.execute(
                sa.text(
                    "INSERT INTO policy_role_permissions (id, role_id, permission_key) "
                    "VALUES (:id, :role_id, :permission_key)"
                ),
                {
                    "id": str(uuid4()),
                    "role_id": role_id,
                    "permission_key": permission_key,
                },
            )

    # Bootstrap: explicit system_admin assignment for existing is_admin users.
    admin_role_id = role_ids["system_admin"]
    admins = conn.execute(sa.text("SELECT id FROM users WHERE is_admin IS TRUE")).fetchall()
    for (user_id,) in admins:
        conn.execute(
            sa.text(
                "INSERT INTO policy_role_assignments "
                "(id, user_id, role_id, organization_id, project_id, created_at, created_by_user_id) "
                "VALUES (:id, :user_id, :role_id, NULL, NULL, NOW(), NULL)"
            ),
            {"id": str(uuid4()), "user_id": user_id, "role_id": admin_role_id},
        )


def downgrade() -> None:
    op.drop_index("uq_policy_assignment_project", table_name="policy_role_assignments")
    op.drop_index("uq_policy_assignment_org", table_name="policy_role_assignments")
    op.drop_index("uq_policy_assignment_system", table_name="policy_role_assignments")
    op.drop_index("ix_policy_role_assignments_project", table_name="policy_role_assignments")
    op.drop_index("ix_policy_role_assignments_org", table_name="policy_role_assignments")
    op.drop_index("ix_policy_role_assignments_user", table_name="policy_role_assignments")
    op.drop_table("policy_role_assignments")
    op.drop_index(
        "ix_policy_role_permissions_permission_key", table_name="policy_role_permissions"
    )
    op.drop_index("ix_policy_role_permissions_role_id", table_name="policy_role_permissions")
    op.drop_table("policy_role_permissions")
    op.drop_index("ix_policy_roles_key", table_name="policy_roles")
    op.drop_table("policy_roles")
    op.drop_table("policy_permissions")
