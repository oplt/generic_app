"""Central authorization policy service."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.lib.app_cache import CacheScope, app_cache, namespaces
from backend.modules.identity_access.models import User
from backend.modules.policy import catalog
from backend.modules.policy.models import PolicyRoleAssignment
from backend.modules.policy.repository import PolicyRepository

logger = logging.getLogger("backend.authz")

_CACHE_TTL_SECONDS = 60


def _permission_cache_key(
    user_id: str,
    *,
    organization_id: str | None,
    project_id: str | None,
) -> str:
    return app_cache.key(
        namespaces.PERMISSIONS,
        "effective",
        scope=CacheScope(
            organization_id=organization_id,
            user_id=user_id,
            project_id=project_id,
        ),
    )


def _user_tag(user_id: str) -> str:
    return f"permissions:user:{user_id}"


def _org_tag(organization_id: str) -> str:
    return f"permissions:org:{organization_id}"


class PolicyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = PolicyRepository(db)

    async def resolve_permissions(
        self,
        user: User,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> set[str]:
        key = _permission_cache_key(
            user.id, organization_id=organization_id, project_id=project_id
        )

        async def loader() -> dict:
            granted = await self._compute_permissions(
                user,
                organization_id=organization_id,
                project_id=project_id,
            )
            return {"permissions": sorted(granted)}

        payload = await app_cache.get_or_set(
            key,
            loader,
            ttl_seconds=_CACHE_TTL_SECONDS,
            tags=[_user_tag(user.id)]
            + ([_org_tag(organization_id)] if organization_id else []),
        )
        if not isinstance(payload, dict):
            return set()
        raw = payload.get("permissions") or []
        return {str(item) for item in raw}

    async def has_permission(
        self,
        user: User,
        action: str,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> bool:
        if action not in catalog.ALL_PERMISSIONS:
            return False
        granted = await self.resolve_permissions(
            user, organization_id=organization_id, project_id=project_id
        )
        return action in granted

    async def authorize(
        self,
        user: User,
        action: str,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        resource: object | None = None,
    ) -> None:
        """Raise 403 unless ``user`` may perform ``action`` in the given scope.

        ``resource`` may be a Project (or any object with ``organization_id`` /
        ``project_id``) when explicit scope kwargs are omitted.
        """

        org_id = organization_id
        proj_id = project_id
        if resource is not None:
            if org_id is None:
                org_id = getattr(resource, "organization_id", None)
            if proj_id is None:
                from backend.modules.projects.models import Project

                if isinstance(resource, Project):
                    proj_id = resource.id
                else:
                    proj_id = getattr(resource, "project_id", None)

        allowed = await self.has_permission(
            user, action, organization_id=org_id, project_id=proj_id
        )
        if allowed:
            return
        logger.warning(
            "authorization_failed action=%s user_id=%s organization_id=%s project_id=%s",
            action,
            user.id,
            org_id,
            proj_id,
        )
        raise HTTPException(status_code=403, detail="Permission denied")

    async def _compute_permissions(
        self,
        user: User,
        *,
        organization_id: str | None,
        project_id: str | None,
    ) -> set[str]:
        granted: set[str] = set()

        # Bootstrap: legacy is_admin flag remains a system-wide superpower until
        # fully migrated onto explicit system_admin assignments.
        if user.is_admin:
            granted.update(catalog.ALL_PERMISSIONS)

        role_by_id = {role.id: role for role in await self.repo.list_roles()}
        if not role_by_id:
            # Catalog not seeded yet — fall back to membership heuristics only.
            return await self._membership_permissions(
                user, organization_id=organization_id, project_id=project_id, granted=granted
            )

        assignments = await self.repo.list_assignments_for_user(user.id)
        applicable_role_ids: list[str] = []
        for assignment in assignments:
            role = role_by_id.get(assignment.role_id)
            if role is None:
                continue
            if role.scope_type == catalog.SCOPE_SYSTEM:
                if assignment.organization_id is None and assignment.project_id is None:
                    applicable_role_ids.append(role.id)
                continue
            if role.scope_type == catalog.SCOPE_ORGANIZATION:
                if (
                    organization_id is not None
                    and assignment.organization_id == organization_id
                    and assignment.project_id is None
                ):
                    applicable_role_ids.append(role.id)
                continue
            if (
                role.scope_type == catalog.SCOPE_PROJECT
                and project_id is not None
                and assignment.project_id == project_id
            ):
                applicable_role_ids.append(role.id)

        granted.update(await self.repo.list_permission_keys_for_role_ids(applicable_role_ids))
        return await self._membership_permissions(
            user, organization_id=organization_id, project_id=project_id, granted=granted
        )

    async def _membership_permissions(
        self,
        user: User,
        *,
        organization_id: str | None,
        project_id: str | None,
        granted: set[str],
    ) -> set[str]:
        del project_id  # membership is org-scoped; project rows use ProjectAccessPort
        if organization_id is None:
            return granted
        memberships = await self.repo.list_memberships_for_user(user.id)
        for membership in memberships:
            if membership.organization_id != organization_id:
                continue
            role = (membership.role or "member").lower()
            if role in {"owner", "admin"}:
                granted.update(catalog.ORG_ADMIN_PERMISSIONS)
            else:
                granted.update(catalog.ORG_MEMBER_PERMISSIONS)
        return granted

    async def invalidate_user(self, user_id: str) -> None:
        await app_cache.invalidate_tags(_user_tag(user_id))

    async def invalidate_organization(self, organization_id: str) -> None:
        await app_cache.invalidate_tags(_org_tag(organization_id))

    async def assign_role(
        self,
        *,
        actor: User,
        user_id: str,
        role_key: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> PolicyRoleAssignment:
        await self.authorize(actor, catalog.ADMIN_MANAGE)
        role = await self.repo.get_role_by_key(role_key)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        self._validate_assignment_scope(role.scope_type, organization_id, project_id)

        existing = await self.repo.get_assignment(
            user_id=user_id,
            role_id=role.id,
            organization_id=organization_id,
            project_id=project_id,
        )
        if existing is not None:
            return existing

        assignment = PolicyRoleAssignment(
            id=str(uuid4()),
            user_id=user_id,
            role_id=role.id,
            organization_id=organization_id,
            project_id=project_id,
            created_by_user_id=actor.id,
        )
        await self.repo.add_assignment(assignment)
        await self.db.commit()
        await self.invalidate_user(user_id)
        if organization_id:
            await self.invalidate_organization(organization_id)
        return assignment

    async def revoke_role(
        self,
        *,
        actor: User,
        user_id: str,
        role_key: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        await self.authorize(actor, catalog.ADMIN_MANAGE)
        role = await self.repo.get_role_by_key(role_key)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        assignment = await self.repo.get_assignment(
            user_id=user_id,
            role_id=role.id,
            organization_id=organization_id,
            project_id=project_id,
        )
        if assignment is None:
            raise HTTPException(status_code=404, detail="Role assignment not found")
        await self.repo.delete_assignment(assignment)
        await self.db.commit()
        await self.invalidate_user(user_id)
        if organization_id:
            await self.invalidate_organization(organization_id)

    @staticmethod
    def _validate_assignment_scope(
        scope_type: str,
        organization_id: str | None,
        project_id: str | None,
    ) -> None:
        if scope_type == catalog.SCOPE_SYSTEM:
            if organization_id is not None or project_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="System roles cannot be scoped to an organization or project",
                )
            return
        if scope_type == catalog.SCOPE_ORGANIZATION:
            if organization_id is None or project_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Organization roles require organization_id and no project_id",
                )
            return
        if scope_type == catalog.SCOPE_PROJECT:
            if project_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Project roles require project_id",
                )
            return
        raise HTTPException(status_code=400, detail=f"Unknown role scope: {scope_type}")
