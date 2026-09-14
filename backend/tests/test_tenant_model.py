"""Multi-organization tenant boundary tests for project ownership scope."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.lib.project_access import SqlAlchemyProjectAccessPort
from backend.modules.projects.service import ProjectsService


class MultiOrgTenantModelTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_scope_uses_project_organization_not_earliest_membership(self):
        port = SqlAlchemyProjectAccessPort(AsyncMock())
        port._repo.get_by_id_for_user = AsyncMock(
            return_value=SimpleNamespace(
                id="project-b",
                owner_id="user-1",
                organization_id="org-b",
            )
        )
        port._identity_repo.get_default_organization_id = AsyncMock(return_value="org-a")

        scope = await port.resolve_ownership_scope("user-1", "project-b")

        self.assertEqual(
            (scope.user_id, scope.project_id, scope.organization_id),
            ("user-1", "project-b", "org-b"),
        )

    async def test_create_project_rejects_organization_without_membership(self):
        service = ProjectsService(AsyncMock())
        service.identity_repo.user_belongs_to_organization = AsyncMock(return_value=False)
        service.repo.create = AsyncMock()

        with self.assertRaises(HTTPException) as raised:
            await service.create_project(
                "owner-1",
                "Cross tenant",
                None,
                organization_id="org-other",
            )
        self.assertEqual(raised.exception.status_code, 403)
        service.repo.create.assert_not_awaited()

    async def test_create_project_stamps_selected_organization(self):
        service = ProjectsService(AsyncMock())
        service.identity_repo.user_belongs_to_organization = AsyncMock(return_value=True)
        created = SimpleNamespace(
            id="project-1",
            owner_id="owner-1",
            organization_id="org-b",
            name="Selected",
            description=None,
            created_at=None,
        )
        service.repo.create = AsyncMock(return_value=created)
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        with patch(
            "backend.modules.projects.service.invalidate_project_list_cache",
            AsyncMock(),
        ):
            project = await service.create_project(
                "owner-1",
                "Selected",
                None,
                organization_id="org-b",
            )

        self.assertIs(project, created)
        service.repo.create.assert_awaited_once_with(
            "owner-1",
            "Selected",
            None,
            organization_id="org-b",
        )

    async def test_assignment_cache_bump_uses_project_organization(self):
        service = ProjectsService(AsyncMock())
        project = SimpleNamespace(id="project-1", owner_id="owner-1", organization_id="org-b")

        with (
            patch(
                "backend.modules.projects.service.invalidate_project_list_cache",
                AsyncMock(),
            ),
            patch(
                "backend.modules.projects.service.bump_corpus_generation",
                AsyncMock(),
            ) as bump,
        ):
            await service._invalidate_assignment_access_caches(
                project=project,
                previous_assignee_id=None,
                new_assignee_id="member-1",
            )

        bump.assert_awaited_once_with(organization_id="org-b", project_id="project-1")


if __name__ == "__main__":
    unittest.main()
