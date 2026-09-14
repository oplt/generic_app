"""Project-list cache invalidation when assignment changes access."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.modules.projects.schemas import ProjectTaskCreate, ProjectTaskUpdate
from backend.modules.projects.service import ProjectsService


def _project():
    return SimpleNamespace(
        id="project-1",
        owner_id="owner-1",
        organization_id="org-1",
        name="P",
    )


def _task(*, assignee_id=None, due_date=None):
    return SimpleNamespace(
        id="task-1",
        project_id="project-1",
        title="Task",
        status="todo",
        assignee_id=assignee_id,
        due_date=due_date,
        priority="medium",
        description=None,
        position=1000,
    )


class ProjectListCacheInvalidationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = ProjectsService(AsyncMock())
        self.service.db.commit = AsyncMock()
        self.service.repo.get_by_id_for_owner = AsyncMock(return_value=_project())
        self.service.repo.get_next_task_position = AsyncMock(return_value=1000)
        self.service.repo.create_task = AsyncMock(return_value=_task(assignee_id="member-1"))
        self.service.repo.get_task_with_assignee = AsyncMock(
            return_value=(_task(assignee_id="member-1"), SimpleNamespace(id="member-1"))
        )
        self.service.repo.get_task_by_id = AsyncMock(
            return_value=_task(assignee_id="member-1")
        )
        self.service.repo.delete_task = AsyncMock()
        self.service._get_assignee_or_404 = AsyncMock(
            return_value=SimpleNamespace(id="member-1")
        )
        self.service._notify_assignment = AsyncMock()
        self.service._notify_due_date_change = AsyncMock()
        self.service._notify_status_change = AsyncMock()
        self.actor = SimpleNamespace(id="owner-1", email="owner@example.com", full_name=None)

    async def test_create_task_invalidates_new_assignee_project_list_after_commit(self):
        order: list[str] = []

        async def commit():
            order.append("commit")

        async def invalidate(user_id: str):
            order.append(f"invalidate:{user_id}")

        self.service.db.commit = commit
        with (
            patch(
                "backend.modules.projects.service.invalidate_project_list_cache",
                side_effect=invalidate,
            ) as invalidate_mock,
            patch(
                "backend.modules.projects.service.bump_corpus_generation",
                AsyncMock(),
            ) as bump_corpus,
        ):
            await self.service.create_task(
                "owner-1",
                self.actor,
                "project-1",
                ProjectTaskCreate(title="Assigned", assignee_id="member-1"),
            )

        invalidate_mock.assert_awaited_once_with("member-1")
        bump_corpus.assert_awaited_once_with(
            organization_id="org-1",
            project_id="project-1",
        )
        self.assertEqual(order, ["commit", "invalidate:member-1"])

    async def test_create_task_without_assignee_skips_project_list_invalidation(self):
        self.service._get_assignee_or_404 = AsyncMock(return_value=None)
        self.service.repo.create_task = AsyncMock(return_value=_task())
        self.service.repo.get_task_with_assignee = AsyncMock(
            return_value=(_task(), None)
        )
        with (
            patch(
                "backend.modules.projects.service.invalidate_project_list_cache",
                AsyncMock(),
            ) as invalidate_mock,
            patch(
                "backend.modules.projects.service.bump_corpus_generation",
                AsyncMock(),
            ) as bump_corpus,
        ):
            await self.service.create_task(
                "owner-1",
                self.actor,
                "project-1",
                ProjectTaskCreate(title="Unassigned"),
            )
        invalidate_mock.assert_not_awaited()
        bump_corpus.assert_not_awaited()

    async def test_reassign_invalidates_previous_and_new_assignee_lists(self):
        task = _task(assignee_id="member-1")
        self.service.repo.get_task_by_id = AsyncMock(return_value=task)
        self.service._get_assignee_or_404 = AsyncMock(
            return_value=SimpleNamespace(id="member-2")
        )
        self.service.repo.get_task_with_assignee = AsyncMock(
            return_value=(_task(assignee_id="member-2"), SimpleNamespace(id="member-2"))
        )
        invalidated: list[str] = []

        async def invalidate(user_id: str):
            invalidated.append(user_id)

        with (
            patch(
                "backend.modules.projects.service.invalidate_project_list_cache",
                side_effect=invalidate,
            ),
            patch(
                "backend.modules.projects.service.bump_corpus_generation",
                AsyncMock(),
            ) as bump_corpus,
        ):
            await self.service.update_task(
                "owner-1",
                self.actor,
                "project-1",
                "task-1",
                ProjectTaskUpdate(assignee_id="member-2"),
            )

        self.assertEqual(invalidated, ["member-1", "member-2"])
        self.assertEqual(task.assignee_id, "member-2")
        bump_corpus.assert_awaited_once_with(
            organization_id="org-1",
            project_id="project-1",
        )

    async def test_remove_assignee_invalidates_previous_assignee_list(self):
        task = _task(assignee_id="member-1")
        self.service.repo.get_task_by_id = AsyncMock(return_value=task)
        self.service._get_assignee_or_404 = AsyncMock(return_value=None)
        self.service.repo.get_task_with_assignee = AsyncMock(
            return_value=(_task(), None)
        )
        with (
            patch(
                "backend.modules.projects.service.invalidate_project_list_cache",
                AsyncMock(),
            ) as invalidate_mock,
            patch(
                "backend.modules.projects.service.bump_corpus_generation",
                AsyncMock(),
            ) as bump_corpus,
        ):
            await self.service.update_task(
                "owner-1",
                self.actor,
                "project-1",
                "task-1",
                ProjectTaskUpdate(assignee_id=None),
            )
        invalidate_mock.assert_awaited_once_with("member-1")
        bump_corpus.assert_awaited_once_with(
            organization_id="org-1",
            project_id="project-1",
        )

    async def test_delete_task_invalidates_assignee_project_list(self):
        self.service.repo.get_task_by_id = AsyncMock(
            return_value=_task(assignee_id="member-1")
        )
        with (
            patch(
                "backend.modules.projects.service.invalidate_project_list_cache",
                AsyncMock(),
            ) as invalidate_mock,
            patch(
                "backend.modules.projects.service.bump_corpus_generation",
                AsyncMock(),
            ) as bump_corpus,
        ):
            await self.service.delete_task("owner-1", "project-1", "task-1")
        invalidate_mock.assert_awaited_once_with("member-1")
        bump_corpus.assert_awaited_once_with(
            organization_id="org-1",
            project_id="project-1",
        )

    async def test_rollback_before_commit_does_not_invalidate_project_list(self):
        self.service.db.commit = AsyncMock(side_effect=RuntimeError("db down"))
        with (
            patch(
                "backend.modules.projects.service.invalidate_project_list_cache",
                AsyncMock(),
            ) as invalidate_mock,
            patch(
                "backend.modules.projects.service.bump_corpus_generation",
                AsyncMock(),
            ) as bump_corpus,
            self.assertRaises(RuntimeError),
        ):
            await self.service.create_task(
                "owner-1",
                self.actor,
                "project-1",
                ProjectTaskCreate(title="Assigned", assignee_id="member-1"),
            )
        invalidate_mock.assert_not_awaited()
        bump_corpus.assert_not_awaited()


class ProjectListCachePatternTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalidate_project_list_deletes_redis_pattern_for_user(self):
        from backend.lib.resource_cache import (
            invalidate_project_list_cache,
            project_list_cache_pattern,
        )

        client = AsyncMock()

        async def scan_iter(*, match, count):
            del count
            self.assertEqual(match, project_list_cache_pattern("member-1"))
            for key in (
                "ga:projects:list:member-1:50:0",
                "ga:projects:list:member-1:50:50",
            ):
                yield key

        client.scan_iter = scan_iter
        client.delete = AsyncMock()

        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", client),
        ):
            mock_settings.CACHE_ENABLED = True
            await invalidate_project_list_cache("member-1")

        client.delete.assert_awaited_once_with(
            "ga:projects:list:member-1:50:0",
            "ga:projects:list:member-1:50:50",
        )
