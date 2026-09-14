"""RBAC / policy persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class PolicyPermission(Base):
    __tablename__ = "policy_permissions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PolicyRole(Base):
    __tablename__ = "policy_roles"
    __table_args__ = (UniqueConstraint("key", name="uq_policy_roles_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    scope_type: Mapped[str] = mapped_column(String(32))  # system|organization|project
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PolicyRolePermission(Base):
    __tablename__ = "policy_role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_key", name="uq_policy_role_permission"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    role_id: Mapped[str] = mapped_column(
        ForeignKey("policy_roles.id", ondelete="CASCADE"), index=True
    )
    permission_key: Mapped[str] = mapped_column(
        ForeignKey("policy_permissions.key", ondelete="CASCADE"), index=True
    )


class PolicyRoleAssignment(Base):
    """Grants a role to a user, optionally scoped to an organization or project."""

    __tablename__ = "policy_role_assignments"
    __table_args__ = (
        Index("ix_policy_role_assignments_user", "user_id"),
        Index("ix_policy_role_assignments_org", "organization_id"),
        Index("ix_policy_role_assignments_project", "project_id"),
        # Partial uniques so NULL org/project scopes do not collide incorrectly.
        Index(
            "uq_policy_assignment_system",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where="organization_id IS NULL AND project_id IS NULL",
        ),
        Index(
            "uq_policy_assignment_org",
            "user_id",
            "role_id",
            "organization_id",
            unique=True,
            postgresql_where="organization_id IS NOT NULL AND project_id IS NULL",
        ),
        Index(
            "uq_policy_assignment_project",
            "user_id",
            "role_id",
            "project_id",
            unique=True,
            postgresql_where="project_id IS NOT NULL",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("policy_roles.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
