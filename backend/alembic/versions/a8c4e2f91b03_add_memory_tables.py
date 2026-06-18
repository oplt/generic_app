"""add memory audit and registry tables

Revision ID: a8c4e2f91b03
Revises: 3f1bfc747f3e
Create Date: 2026-06-16 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8c4e2f91b03"
down_revision: str | Sequence[str] | None = "3f1bfc747f3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_audit_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("external_memory_id", sa.String(length=128), nullable=True),
        sa.Column("memory_level", sa.String(length=32), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memory_audit_logs_user_id"), "memory_audit_logs", ["user_id"])
    op.create_index(op.f("ix_memory_audit_logs_agent_id"), "memory_audit_logs", ["agent_id"])
    op.create_index(op.f("ix_memory_audit_logs_run_id"), "memory_audit_logs", ["run_id"])
    op.create_index(op.f("ix_memory_audit_logs_project_id"), "memory_audit_logs", ["project_id"])
    op.create_index(op.f("ix_memory_audit_logs_operation"), "memory_audit_logs", ["operation"])
    op.create_index(
        op.f("ix_memory_audit_logs_external_memory_id"),
        "memory_audit_logs",
        ["external_memory_id"],
    )
    op.create_index(
        op.f("ix_memory_audit_logs_memory_level"), "memory_audit_logs", ["memory_level"]
    )
    op.create_index(op.f("ix_memory_audit_logs_created_at"), "memory_audit_logs", ["created_at"])

    op.create_table(
        "memory_registry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("external_memory_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("memory_level", sa.String(length=32), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_memory_id"),
    )
    op.create_index(
        op.f("ix_memory_registry_external_memory_id"),
        "memory_registry",
        ["external_memory_id"],
    )
    op.create_index(op.f("ix_memory_registry_user_id"), "memory_registry", ["user_id"])
    op.create_index(op.f("ix_memory_registry_agent_id"), "memory_registry", ["agent_id"])
    op.create_index(op.f("ix_memory_registry_run_id"), "memory_registry", ["run_id"])
    op.create_index(op.f("ix_memory_registry_project_id"), "memory_registry", ["project_id"])
    op.create_index(op.f("ix_memory_registry_memory_level"), "memory_registry", ["memory_level"])
    op.create_index(op.f("ix_memory_registry_status"), "memory_registry", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_memory_registry_status"), table_name="memory_registry")
    op.drop_index(op.f("ix_memory_registry_memory_level"), table_name="memory_registry")
    op.drop_index(op.f("ix_memory_registry_project_id"), table_name="memory_registry")
    op.drop_index(op.f("ix_memory_registry_run_id"), table_name="memory_registry")
    op.drop_index(op.f("ix_memory_registry_agent_id"), table_name="memory_registry")
    op.drop_index(op.f("ix_memory_registry_user_id"), table_name="memory_registry")
    op.drop_index(op.f("ix_memory_registry_external_memory_id"), table_name="memory_registry")
    op.drop_table("memory_registry")

    op.drop_index(op.f("ix_memory_audit_logs_created_at"), table_name="memory_audit_logs")
    op.drop_index(op.f("ix_memory_audit_logs_memory_level"), table_name="memory_audit_logs")
    op.drop_index(
        op.f("ix_memory_audit_logs_external_memory_id"), table_name="memory_audit_logs"
    )
    op.drop_index(op.f("ix_memory_audit_logs_operation"), table_name="memory_audit_logs")
    op.drop_index(op.f("ix_memory_audit_logs_project_id"), table_name="memory_audit_logs")
    op.drop_index(op.f("ix_memory_audit_logs_run_id"), table_name="memory_audit_logs")
    op.drop_index(op.f("ix_memory_audit_logs_agent_id"), table_name="memory_audit_logs")
    op.drop_index(op.f("ix_memory_audit_logs_user_id"), table_name="memory_audit_logs")
    op.drop_table("memory_audit_logs")
