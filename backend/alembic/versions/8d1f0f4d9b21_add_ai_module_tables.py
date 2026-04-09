"""add ai module tables

Revision ID: 8d1f0f4d9b21
Revises: 4f5d09314a82
Create Date: 2026-04-08 23:59:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d1f0f4d9b21"
down_revision: Union[str, None] = "4f5d09314a82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_prompt_templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("active_version_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_prompt_templates_key"), "ai_prompt_templates", ["key"], unique=False)
    op.create_index(op.f("ix_ai_prompt_templates_user_id"), "ai_prompt_templates", ["user_id"], unique=False)

    op.create_table(
        "ai_prompt_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("prompt_template_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_prompt_template", sa.Text(), nullable=False),
        sa.Column("variable_definitions_json", sa.JSON(), nullable=False),
        sa.Column("response_format", sa.String(length=32), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("rollout_percentage", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("input_cost_per_million", sa.Integer(), nullable=False),
        sa.Column("output_cost_per_million", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_template_id"], ["ai_prompt_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_prompt_versions_prompt_template_id"), "ai_prompt_versions", ["prompt_template_id"], unique=False)
    op.create_foreign_key(
        "fk_ai_prompt_templates_active_version_id",
        "ai_prompt_templates",
        "ai_prompt_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "ai_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("ingestion_status", sa.String(length=32), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_documents_user_id"), "ai_documents", ["user_id"], unique=False)

    op.create_table(
        "ai_document_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["ai_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_document_chunks_document_id"), "ai_document_chunks", ["document_id"], unique=False)

    op.create_table(
        "ai_evaluation_datasets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_evaluation_datasets_user_id"), "ai_evaluation_datasets", ["user_id"], unique=False)

    op.create_table(
        "ai_evaluation_cases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("input_variables_json", sa.JSON(), nullable=False),
        sa.Column("expected_output_text", sa.Text(), nullable=True),
        sa.Column("expected_output_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["ai_evaluation_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_evaluation_cases_dataset_id"), "ai_evaluation_cases", ["dataset_id"], unique=False)

    op.create_table(
        "ai_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("prompt_template_id", sa.String(), nullable=True),
        sa.Column("prompt_version_id", sa.String(), nullable=True),
        sa.Column("evaluation_dataset_id", sa.String(), nullable=True),
        sa.Column("evaluation_case_id", sa.String(), nullable=True),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_format", sa.String(length=32), nullable=False),
        sa.Column("variables_json", sa.JSON(), nullable=False),
        sa.Column("retrieval_query", sa.Text(), nullable=True),
        sa.Column("retrieved_chunk_ids_json", sa.JSON(), nullable=False),
        sa.Column("input_messages_json", sa.JSON(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["evaluation_case_id"], ["ai_evaluation_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evaluation_dataset_id"], ["ai_evaluation_datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_template_id"], ["ai_prompt_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["ai_prompt_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_runs_user_id"), "ai_runs", ["user_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_prompt_template_id"), "ai_runs", ["prompt_template_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_prompt_version_id"), "ai_runs", ["prompt_version_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_evaluation_dataset_id"), "ai_runs", ["evaluation_dataset_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_evaluation_case_id"), "ai_runs", ["evaluation_case_id"], unique=False)

    op.create_table(
        "ai_review_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("requested_by_user_id", sa.String(), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("corrected_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["ai_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_review_items_run_id"), "ai_review_items", ["run_id"], unique=False)
    op.create_index(op.f("ix_ai_review_items_requested_by_user_id"), "ai_review_items", ["requested_by_user_id"], unique=False)
    op.create_index(op.f("ix_ai_review_items_assigned_to_user_id"), "ai_review_items", ["assigned_to_user_id"], unique=False)
    op.create_index(op.f("ix_ai_review_items_reviewed_by_user_id"), "ai_review_items", ["reviewed_by_user_id"], unique=False)

    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("corrected_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_feedback_run_id"), "ai_feedback", ["run_id"], unique=False)
    op.create_index(op.f("ix_ai_feedback_user_id"), "ai_feedback", ["user_id"], unique=False)

    op.create_table(
        "ai_evaluation_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("prompt_version_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("average_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["ai_evaluation_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["ai_prompt_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_evaluation_runs_dataset_id"), "ai_evaluation_runs", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_ai_evaluation_runs_prompt_version_id"), "ai_evaluation_runs", ["prompt_version_id"], unique=False)
    op.create_index(op.f("ix_ai_evaluation_runs_user_id"), "ai_evaluation_runs", ["user_id"], unique=False)

    op.create_table(
        "ai_evaluation_run_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("evaluation_run_id", sa.String(), nullable=False),
        sa.Column("evaluation_case_id", sa.String(), nullable=False),
        sa.Column("ai_run_id", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["ai_run_id"], ["ai_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_case_id"], ["ai_evaluation_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["ai_evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_evaluation_run_items_evaluation_run_id"), "ai_evaluation_run_items", ["evaluation_run_id"], unique=False)
    op.create_index(op.f("ix_ai_evaluation_run_items_evaluation_case_id"), "ai_evaluation_run_items", ["evaluation_case_id"], unique=False)
    op.create_index(op.f("ix_ai_evaluation_run_items_ai_run_id"), "ai_evaluation_run_items", ["ai_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_evaluation_run_items_ai_run_id"), table_name="ai_evaluation_run_items")
    op.drop_index(op.f("ix_ai_evaluation_run_items_evaluation_case_id"), table_name="ai_evaluation_run_items")
    op.drop_index(op.f("ix_ai_evaluation_run_items_evaluation_run_id"), table_name="ai_evaluation_run_items")
    op.drop_table("ai_evaluation_run_items")
    op.drop_index(op.f("ix_ai_evaluation_runs_user_id"), table_name="ai_evaluation_runs")
    op.drop_index(op.f("ix_ai_evaluation_runs_prompt_version_id"), table_name="ai_evaluation_runs")
    op.drop_index(op.f("ix_ai_evaluation_runs_dataset_id"), table_name="ai_evaluation_runs")
    op.drop_table("ai_evaluation_runs")
    op.drop_index(op.f("ix_ai_feedback_user_id"), table_name="ai_feedback")
    op.drop_index(op.f("ix_ai_feedback_run_id"), table_name="ai_feedback")
    op.drop_table("ai_feedback")
    op.drop_index(op.f("ix_ai_review_items_reviewed_by_user_id"), table_name="ai_review_items")
    op.drop_index(op.f("ix_ai_review_items_assigned_to_user_id"), table_name="ai_review_items")
    op.drop_index(op.f("ix_ai_review_items_requested_by_user_id"), table_name="ai_review_items")
    op.drop_index(op.f("ix_ai_review_items_run_id"), table_name="ai_review_items")
    op.drop_table("ai_review_items")
    op.drop_index(op.f("ix_ai_runs_evaluation_case_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_evaluation_dataset_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_prompt_version_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_prompt_template_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_user_id"), table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_index(op.f("ix_ai_evaluation_cases_dataset_id"), table_name="ai_evaluation_cases")
    op.drop_table("ai_evaluation_cases")
    op.drop_index(op.f("ix_ai_evaluation_datasets_user_id"), table_name="ai_evaluation_datasets")
    op.drop_table("ai_evaluation_datasets")
    op.drop_index(op.f("ix_ai_document_chunks_document_id"), table_name="ai_document_chunks")
    op.drop_table("ai_document_chunks")
    op.drop_index(op.f("ix_ai_documents_user_id"), table_name="ai_documents")
    op.drop_table("ai_documents")
    op.drop_constraint("fk_ai_prompt_templates_active_version_id", "ai_prompt_templates", type_="foreignkey")
    op.drop_index(op.f("ix_ai_prompt_versions_prompt_template_id"), table_name="ai_prompt_versions")
    op.drop_table("ai_prompt_versions")
    op.drop_index(op.f("ix_ai_prompt_templates_user_id"), table_name="ai_prompt_templates")
    op.drop_index(op.f("ix_ai_prompt_templates_key"), table_name="ai_prompt_templates")
    op.drop_table("ai_prompt_templates")
