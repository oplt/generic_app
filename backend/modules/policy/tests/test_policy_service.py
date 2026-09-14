"""RBAC / policy authorization tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from backend.modules.policy import catalog
from backend.modules.policy.service import PolicyService


def _user(*, user_id: str = "user-1", is_admin: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, is_admin=is_admin)


def _role(*, role_id: str, key: str, scope_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=role_id, key=key, scope_type=scope_type)


def _assignment(
    *,
    role_id: str,
    organization_id: str | None = None,
    project_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        role_id=role_id,
        organization_id=organization_id,
        project_id=project_id,
    )


def _membership(*, organization_id: str, role: str = "member") -> SimpleNamespace:
    return SimpleNamespace(organization_id=organization_id, role=role)


class PolicyAuthorizeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = MagicMock()
        self.service = PolicyService(self.db)
        self.service.repo = MagicMock()
        # Bypass cache for unit tests — exercise _compute_permissions directly.
        self.service.resolve_permissions = (  # type: ignore[method-assign]
            lambda user, organization_id=None, project_id=None: self.service._compute_permissions(
                user, organization_id=organization_id, project_id=project_id
            )
        )

    async def test_is_admin_grants_all_capabilities(self) -> None:
        self.service.repo.list_roles = AsyncMock(return_value=[])
        self.service.repo.list_memberships_for_user = AsyncMock(return_value=[])
        granted = await self.service.resolve_permissions(_user(is_admin=True))
        self.assertIn(catalog.ADMIN_MANAGE, granted)
        self.assertIn(catalog.RAG_MANAGE, granted)

    async def test_cross_tenant_membership_does_not_leak(self) -> None:
        self.service.repo.list_roles = AsyncMock(return_value=[])
        self.service.repo.list_memberships_for_user = AsyncMock(
            return_value=[_membership(organization_id="org-a", role="owner")]
        )
        in_a = await self.service.resolve_permissions(
            _user(), organization_id="org-a"
        )
        in_b = await self.service.resolve_permissions(
            _user(), organization_id="org-b"
        )
        self.assertIn(catalog.PROJECT_CREATE, in_a)
        self.assertNotIn(catalog.PROJECT_CREATE, in_b)
        self.assertNotIn(catalog.ADMIN_MANAGE, in_a)

    async def test_org_assignment_scoped_to_organization(self) -> None:
        org_admin = _role(role_id="r1", key=catalog.ROLE_ORG_ADMIN, scope_type="organization")
        self.service.repo.list_roles = AsyncMock(return_value=[org_admin])
        self.service.repo.list_assignments_for_user = AsyncMock(
            return_value=[_assignment(role_id="r1", organization_id="org-a")]
        )
        self.service.repo.list_permission_keys_for_role_ids = AsyncMock(
            side_effect=lambda role_ids: set(catalog.ORG_ADMIN_PERMISSIONS)
            if role_ids
            else set()
        )
        self.service.repo.list_memberships_for_user = AsyncMock(return_value=[])

        allowed = await self.service.has_permission(
            _user(), catalog.RAG_MANAGE, organization_id="org-a"
        )
        denied = await self.service.has_permission(
            _user(), catalog.RAG_MANAGE, organization_id="org-b"
        )
        self.assertTrue(allowed)
        self.assertFalse(denied)

    async def test_project_assignment_does_not_escalate_to_other_project(self) -> None:
        editor = _role(
            role_id="r2", key=catalog.ROLE_PROJECT_EDITOR, scope_type="project"
        )
        self.service.repo.list_roles = AsyncMock(return_value=[editor])
        self.service.repo.list_assignments_for_user = AsyncMock(
            return_value=[_assignment(role_id="r2", project_id="proj-1")]
        )
        self.service.repo.list_permission_keys_for_role_ids = AsyncMock(
            side_effect=lambda role_ids: set(catalog.PROJECT_EDITOR_PERMISSIONS)
            if role_ids
            else set()
        )
        self.service.repo.list_memberships_for_user = AsyncMock(return_value=[])

        self.assertTrue(
            await self.service.has_permission(
                _user(), catalog.RAG_MANAGE, project_id="proj-1"
            )
        )
        self.assertFalse(
            await self.service.has_permission(
                _user(), catalog.RAG_MANAGE, project_id="proj-2"
            )
        )

    async def test_authorize_raises_on_denial(self) -> None:
        self.service.repo.list_roles = AsyncMock(return_value=[])
        self.service.repo.list_memberships_for_user = AsyncMock(return_value=[])
        with self.assertRaises(HTTPException) as ctx:
            await self.service.authorize(_user(), catalog.ADMIN_MANAGE)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_assign_role_requires_admin_manage(self) -> None:
        self.service.repo.list_roles = AsyncMock(return_value=[])
        self.service.repo.list_memberships_for_user = AsyncMock(return_value=[])
        with self.assertRaises(HTTPException) as ctx:
            await self.service.assign_role(
                actor=_user(is_admin=False),
                user_id="user-2",
                role_key=catalog.ROLE_SYSTEM_ADMIN,
            )
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_stale_permission_cache_invalidated_on_assignment(self) -> None:
        invalidate = AsyncMock()
        with (
            patch.object(self.service, "invalidate_user", invalidate),
            patch.object(self.service, "authorize", AsyncMock()),
        ):
            role = _role(
                role_id="r-admin",
                key=catalog.ROLE_SYSTEM_ADMIN,
                scope_type="system",
            )
            self.service.repo.get_role_by_key = AsyncMock(return_value=role)
            self.service.repo.get_assignment = AsyncMock(return_value=None)
            self.service.repo.add_assignment = AsyncMock(
                side_effect=lambda assignment: assignment
            )
            self.db.commit = AsyncMock()
            await self.service.assign_role(
                actor=_user(is_admin=True),
                user_id="user-2",
                role_key=catalog.ROLE_SYSTEM_ADMIN,
            )
        invalidate.assert_awaited_with("user-2")


class PolicyCacheKeyTest(unittest.IsolatedAsyncioTestCase):
    async def test_cached_resolution_uses_app_cache_and_tags(self) -> None:
        db = MagicMock()
        service = PolicyService(db)
        service._compute_permissions = AsyncMock(  # type: ignore[method-assign]
            return_value={catalog.PROJECT_READ}
        )
        get_or_set = AsyncMock(return_value={"permissions": [catalog.PROJECT_READ]})
        with patch("backend.modules.policy.service.app_cache") as cache:
            cache.key.side_effect = (
                lambda *args, **kwargs: "ga:v1:permissions:org:org-1:user:u1:project:_:effective"
            )
            cache.get_or_set = get_or_set
            granted = await service.resolve_permissions(
                _user(user_id="u1"), organization_id="org-1"
            )
        self.assertEqual(granted, {catalog.PROJECT_READ})
        get_or_set.assert_awaited()
        kwargs = get_or_set.await_args.kwargs
        self.assertIn("permissions:user:u1", kwargs["tags"])
        self.assertIn("permissions:org:org-1", kwargs["tags"])
