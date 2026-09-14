"""add jobs.cancel permission for operational console

Revision ID: l2b9d4e5f150
Revises: k1a8c2d3e049
Create Date: 2026-09-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "l2b9d4e5f150"
down_revision: str | Sequence[str] | None = "k1a8c2d3e049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO policy_permissions (key, description, created_at) "
            "VALUES ('jobs.cancel', 'Cancel queued jobs', NOW()) "
            "ON CONFLICT (key) DO NOTHING"
        )
    )
    roles = conn.execute(
        sa.text(
            "SELECT id FROM policy_roles "
            "WHERE key IN ('system_admin', 'org_admin', 'project_editor')"
        )
    ).fetchall()
    for (role_id,) in roles:
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM policy_role_permissions "
                "WHERE role_id = :role_id AND permission_key = 'jobs.cancel'"
            ),
            {"role_id": role_id},
        ).fetchone()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO policy_role_permissions (id, role_id, permission_key) "
                "VALUES (:id, :role_id, 'jobs.cancel')"
            ),
            {"id": str(uuid4()), "role_id": role_id},
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM policy_role_permissions WHERE permission_key = 'jobs.cancel'"
        )
    )
    op.execute(sa.text("DELETE FROM policy_permissions WHERE key = 'jobs.cancel'"))
