"""Policy persistence helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import OrganizationMembership
from backend.modules.policy.models import (
    PolicyPermission,
    PolicyRole,
    PolicyRoleAssignment,
    PolicyRolePermission,
)


class PolicyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_permissions(self) -> list[PolicyPermission]:
        result = await self.db.execute(select(PolicyPermission).order_by(PolicyPermission.key))
        return list(result.scalars().all())

    async def list_roles(self) -> list[PolicyRole]:
        result = await self.db.execute(select(PolicyRole).order_by(PolicyRole.key))
        return list(result.scalars().all())

    async def get_role_by_key(self, key: str) -> PolicyRole | None:
        result = await self.db.execute(select(PolicyRole).where(PolicyRole.key == key))
        return result.scalar_one_or_none()

    async def get_role_by_id(self, role_id: str) -> PolicyRole | None:
        result = await self.db.execute(select(PolicyRole).where(PolicyRole.id == role_id))
        return result.scalar_one_or_none()

    async def list_permission_keys_for_role_ids(self, role_ids: list[str]) -> set[str]:
        if not role_ids:
            return set()
        result = await self.db.execute(
            select(PolicyRolePermission.permission_key).where(
                PolicyRolePermission.role_id.in_(role_ids)
            )
        )
        return {row[0] for row in result.all()}

    async def list_assignments_for_user(self, user_id: str) -> list[PolicyRoleAssignment]:
        result = await self.db.execute(
            select(PolicyRoleAssignment).where(PolicyRoleAssignment.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_memberships_for_user(self, user_id: str) -> list[OrganizationMembership]:
        result = await self.db.execute(
            select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_assignment(
        self,
        *,
        user_id: str,
        role_id: str,
        organization_id: str | None,
        project_id: str | None,
    ) -> PolicyRoleAssignment | None:
        stmt = select(PolicyRoleAssignment).where(
            PolicyRoleAssignment.user_id == user_id,
            PolicyRoleAssignment.role_id == role_id,
        )
        if organization_id is None:
            stmt = stmt.where(PolicyRoleAssignment.organization_id.is_(None))
        else:
            stmt = stmt.where(PolicyRoleAssignment.organization_id == organization_id)
        if project_id is None:
            stmt = stmt.where(PolicyRoleAssignment.project_id.is_(None))
        else:
            stmt = stmt.where(PolicyRoleAssignment.project_id == project_id)
        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def add_assignment(self, assignment: PolicyRoleAssignment) -> PolicyRoleAssignment:
        self.db.add(assignment)
        await self.db.flush()
        return assignment

    async def delete_assignment(self, assignment: PolicyRoleAssignment) -> None:
        await self.db.delete(assignment)
        await self.db.flush()

    async def list_assignments_for_user_detailed(
        self, user_id: str
    ) -> list[tuple[PolicyRoleAssignment, PolicyRole]]:
        result = await self.db.execute(
            select(PolicyRoleAssignment, PolicyRole)
            .join(PolicyRole, PolicyRole.id == PolicyRoleAssignment.role_id)
            .where(PolicyRoleAssignment.user_id == user_id)
            .order_by(PolicyRole.key)
        )
        return list(result.all())
