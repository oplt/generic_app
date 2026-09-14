"""add rag evaluation workbench tables

Revision ID: k1a8c2d3e049
Revises: j0f7b5d1e148
Create Date: 2026-09-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "k1a8c2d3e049"
down_revision: str | Sequence[str] | None = "j0f7b5d1e148"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_evaluation_datasets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rag_evaluation_datasets_organization_id"),
        "rag_evaluation_datasets",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rag_evaluation_datasets_user_id"),
        "rag_evaluation_datasets",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "rag_evaluation_cases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_document_ids_json", sa.JSON(), nullable=False),
        sa.Column("expected_chunk_ids_json", sa.JSON(), nullable=False),
        sa.Column("expected_sources_json", sa.JSON(), nullable=False),
        sa.Column("expected_facts_json", sa.JSON(), nullable=False),
        sa.Column("judgments_json", sa.JSON(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["rag_evaluation_datasets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rag_evaluation_cases_dataset_id"),
        "rag_evaluation_cases",
        ["dataset_id"],
        unique=False,
    )

    op.create_table(
        "rag_evaluation_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("latency_json", sa.JSON(), nullable=False),
        sa.Column("baseline_run_id", sa.String(), nullable=True),
        sa.Column("comparison_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["rag_evaluation_datasets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rag_evaluation_runs_baseline_run_id"),
        "rag_evaluation_runs",
        ["baseline_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rag_evaluation_runs_dataset_id"),
        "rag_evaluation_runs",
        ["dataset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rag_evaluation_runs_organization_id"),
        "rag_evaluation_runs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rag_evaluation_runs_status"),
        "rag_evaluation_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rag_evaluation_runs_user_id"),
        "rag_evaluation_runs",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "rag_evaluation_run_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("ranked_chunk_ids_json", sa.JSON(), nullable=False),
        sa.Column("candidates_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("latency_json", sa.JSON(), nullable=False),
        sa.Column("included_in_context", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["rag_evaluation_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["rag_evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rag_evaluation_run_items_case_id"),
        "rag_evaluation_run_items",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rag_evaluation_run_items_run_id"),
        "rag_evaluation_run_items",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_rag_evaluation_run_items_run_id"), table_name="rag_evaluation_run_items"
    )
    op.drop_index(
        op.f("ix_rag_evaluation_run_items_case_id"), table_name="rag_evaluation_run_items"
    )
    op.drop_table("rag_evaluation_run_items")
    op.drop_index(op.f("ix_rag_evaluation_runs_user_id"), table_name="rag_evaluation_runs")
    op.drop_index(op.f("ix_rag_evaluation_runs_status"), table_name="rag_evaluation_runs")
    op.drop_index(
        op.f("ix_rag_evaluation_runs_organization_id"), table_name="rag_evaluation_runs"
    )
    op.drop_index(op.f("ix_rag_evaluation_runs_dataset_id"), table_name="rag_evaluation_runs")
    op.drop_index(
        op.f("ix_rag_evaluation_runs_baseline_run_id"), table_name="rag_evaluation_runs"
    )
    op.drop_table("rag_evaluation_runs")
    op.drop_index(op.f("ix_rag_evaluation_cases_dataset_id"), table_name="rag_evaluation_cases")
    op.drop_table("rag_evaluation_cases")
    op.drop_index(
        op.f("ix_rag_evaluation_datasets_user_id"), table_name="rag_evaluation_datasets"
    )
    op.drop_index(
        op.f("ix_rag_evaluation_datasets_organization_id"),
        table_name="rag_evaluation_datasets",
    )
    op.drop_table("rag_evaluation_datasets")
