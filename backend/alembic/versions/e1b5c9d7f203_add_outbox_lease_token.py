"""Add a token for compare-and-set outbox acknowledgements.

Revision ID: e1b5c9d7f203
Revises: c7f1a9d2e804
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1b5c9d7f203"
down_revision: str | Sequence[str] | None = "c7f1a9d2e804"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "background_job_outbox",
        sa.Column("lease_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_background_job_outbox_lease_token",
        "background_job_outbox",
        ["lease_token"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_background_job_outbox_lease_token", table_name="background_job_outbox")
    op.drop_column("background_job_outbox", "lease_token")
