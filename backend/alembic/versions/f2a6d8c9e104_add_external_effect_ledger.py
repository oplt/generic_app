"""add logical Celery operation IDs and external effect ledger

Revision ID: f2a6d8c9e104
Revises: e1b5c9d7f203
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a6d8c9e104"
down_revision: str | Sequence[str] | None = "e1b5c9d7f203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_jobs",
        sa.Column("operation_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_application_jobs_operation_id",
        "application_jobs",
        ["operation_id"],
        unique=True,
        postgresql_where=sa.text("operation_id IS NOT NULL"),
    )
    op.create_table(
        "external_effects",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("operation_id", sa.String(length=128), nullable=False),
        sa.Column("effect_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider_idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id",
            "effect_type",
            name="uq_external_effects_operation_type",
        ),
    )
    op.create_index(
        "ix_external_effects_status",
        "external_effects",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_external_effects_operation_id",
        "external_effects",
        ["operation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_external_effects_operation_id", table_name="external_effects")
    op.drop_index("ix_external_effects_status", table_name="external_effects")
    op.drop_table("external_effects")
    op.drop_index("uq_application_jobs_operation_id", table_name="application_jobs")
    op.drop_column("application_jobs", "operation_id")
