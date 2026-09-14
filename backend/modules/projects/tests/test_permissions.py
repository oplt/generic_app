from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from backend.modules.projects.schemas import (
    ProjectTaskCreate,
    ProjectTaskReorderRequest,
    ProjectTaskUpdate,
)
from backend.modules.projects.service import ProjectsService


class ProjectMutationPermissionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = ProjectsService(AsyncMock())
        self.service.repo.get_by_id_for_owner = AsyncMock(return_value=None)
        self.service.repo.get_by_id_for_user = AsyncMock(
            return_value=SimpleNamespace(id="project-1", owner_id="owner-1")
        )
        self.actor = SimpleNamespace(id="member-1", email="member@example.com", full_name=None)

    async def test_assignee_read_access_does_not_authorize_any_task_mutation(self):
        mutations = (
            self.service.create_task(
                "member-1",
                self.actor,
                "project-1",
                ProjectTaskCreate(title="Create task"),
            ),
            self.service.update_task(
                "member-1",
                self.actor,
                "project-1",
                "task-1",
                ProjectTaskUpdate(status="done"),
            ),
            self.service.delete_task("member-1", "project-1", "task-1"),
            self.service.reorder_tasks(
                "member-1",
                self.actor,
                "project-1",
                ProjectTaskReorderRequest(columns=[]),
            ),
        )

        for mutation in mutations:
            with self.assertRaises(HTTPException) as raised:
                await mutation
            self.assertEqual(raised.exception.status_code, 404)

        self.assertEqual(self.service.repo.get_by_id_for_owner.await_count, 4)
        self.service.repo.get_by_id_for_user.assert_not_awaited()

    async def test_assignee_must_belong_to_project_organization(self):
        project = SimpleNamespace(id="project-1", owner_id="owner-1", organization_id="org-1")
        assignee = SimpleNamespace(id="member-1")
        self.service.users_repo.get_active_user_in_organization = AsyncMock(
            return_value=assignee
        )

        result = await self.service._get_assignee_or_404(project, "member-1")

        self.assertIs(result, assignee)
        self.service.users_repo.get_active_user_in_organization.assert_awaited_once_with(
            "member-1", "org-1"
        )

        self.service.users_repo.get_active_user_in_organization.return_value = None
        with self.assertRaises(HTTPException) as raised:
            await self.service._get_assignee_or_404(project, "different-org-user")
        self.assertEqual(raised.exception.status_code, 404)
