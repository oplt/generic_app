"""add rag_index_versions for pipeline lifecycle

Revision ID: i9e6a4c0d037
Revises: h8d5f3b1c926
Create Date: 2026-09-14 19:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i9e6a4c0d037"
down_revision: Union[str, Sequence[str], None] = "h8d5f3b1c926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_index_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_schema_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_rag_index_versions_key"), "rag_index_versions", ["key"], unique=False)
    op.create_index(
        op.f("ix_rag_index_versions_status"), "rag_index_versions", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rag_index_versions_status"), table_name="rag_index_versions")
    op.drop_index(op.f("ix_rag_index_versions_key"), table_name="rag_index_versions")
    op.drop_table("rag_index_versions")
