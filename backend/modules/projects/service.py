import asyncio
from datetime import date

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from backend.lib.resource_cache import (
    get_cached_model_list,
    invalidate_calendar_cache,
    invalidate_project_list_cache,
    project_list_cache_key,
    set_cached_model_list,
)
from backend.lib.retrieval_cache import bump_corpus_generation
from backend.modules.identity_access.models import User
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.notifications.repository import NotificationsRepository
from backend.modules.projects.models import Project, ProjectTask
from backend.modules.projects.repository import TASK_POSITION_GAP, ProjectsRepository
from backend.modules.projects.schemas import (
    ProjectResponse,
    ProjectTaskCreate,
    ProjectTaskReorderRequest,
    ProjectTaskUpdate,
)
from backend.modules.users.repository import UsersRepository


class ProjectsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProjectsRepository(db)
        self.users_repo = UsersRepository(db)
        self.identity_repo = IdentityRepository(db)
        self.notifications_repo = NotificationsRepository(db)

    async def create_project(
        self,
        owner_id: str,
        name: str,
        description: str | None,
        *,
        organization_id: str | None = None,
    ) -> Project:
        resolved_organization_id = await self._resolve_project_organization_id(
            owner_id, organization_id
        )
        project = await self.repo.create(
            owner_id,
            name,
            description,
            organization_id=resolved_organization_id,
        )
        await self.db.commit()
        await self.db.refresh(project)
        await invalidate_project_list_cache(owner_id)
        return project

    async def _resolve_project_organization_id(
        self,
        owner_id: str,
        organization_id: str | None,
    ) -> str:
        if organization_id is not None:
            belongs = await self.identity_repo.user_belongs_to_organization(
                owner_id, organization_id
            )
            if not belongs:
                raise HTTPException(status_code=403, detail="Organization access denied")
            return organization_id
        default_organization_id = await self.identity_repo.get_default_organization_id(
            owner_id
        )
        if default_organization_id is not None:
            return default_organization_id
        user = await self.identity_repo.get_user_by_id(owner_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        organization = await self.identity_repo.create_personal_organization(user)
        return organization.id

    async def project_summary(self, user_id: str) -> tuple[int, int]:
        return await self.repo.summary_for_user(user_id)

    async def list_projects(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[ProjectResponse], int]:
        cache_key = project_list_cache_key(user_id, limit, offset)
        cached = await get_cached_model_list(cache_key, ProjectResponse)
        if cached is not None:
            return cached

        projects, total = await self.repo.list_accessible_by_user(
            user_id, limit=limit, offset=offset
        )
        items = [
            ProjectResponse(
                id=project.id,
                organization_id=project.organization_id,
                name=project.name,
                description=project.description,
                created_at=project.created_at,
            )
            for project in projects
        ]
        await set_cached_model_list(
            cache_key,
            items,
            total=total,
            ttl_seconds=settings.CACHE_PROJECT_LIST_TTL_SECONDS,
        )
        return items, total

    async def list_projects_cursor(self, user_id: str, *, limit: int, cursor: str | None):
        projects, next_cursor, has_more = await self.repo.list_accessible_by_user_cursor(
            user_id, limit=limit, cursor=cursor
        )
        return (
            [
                ProjectResponse(
                    id=project.id,
                    organization_id=project.organization_id,
                    name=project.name,
                    description=project.description,
                    created_at=project.created_at,
                )
                for project in projects
            ],
            next_cursor,
            has_more,
        )

    async def get_project(self, user_id: str, project_id: str) -> Project:
        return await self._get_project_or_404(user_id, project_id)

    async def list_tasks(
        self,
        user_id: str,
        project_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[tuple[ProjectTask, User | None]], int]:
        project = await self._get_project_or_404(user_id, project_id)
        return await self.repo.list_tasks_with_assignees(project.id, limit=limit, offset=offset)

    async def list_tasks_cursor(
        self, user_id: str, project_id: str, *, limit: int, cursor: str | None
    ):
        project = await self._get_project_or_404(user_id, project_id)
        return await self.repo.list_tasks_with_assignees_cursor(
            project.id, limit=limit, cursor=cursor
        )

    async def create_task(
        self,
        user_id: str,
        actor: User,
        project_id: str,
        payload: ProjectTaskCreate,
    ) -> tuple[ProjectTask, User | None]:
        project = await self._get_owned_project_or_404(user_id, project_id)
        assignee = await self._get_assignee_or_404(project, payload.assignee_id)
        position = await self.repo.get_next_task_position(project.id, payload.status)
        task = await self.repo.create_task(
            project_id=project.id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
            priority=payload.priority,
            due_date=payload.due_date,
            assignee_id=assignee.id if assignee else None,
            position=position,
        )

        await self._notify_assignment(project, task, actor, None, assignee)
        await self._notify_due_date_change(project, task, actor, None, assignee)

        await self.db.commit()
        task_row = await self.repo.get_task_with_assignee(project.id, task.id)
        if not task_row:
            raise HTTPException(status_code=500, detail="Failed to load created task")
        await self._invalidate_assignment_access_caches(
            project=project,
            previous_assignee_id=None,
            new_assignee_id=assignee.id if assignee else None,
        )
        if payload.due_date is not None:
            await invalidate_calendar_cache(user_id)
            if assignee and assignee.id != user_id:
                await invalidate_calendar_cache(assignee.id)
        return task_row

    async def update_task(
        self,
        user_id: str,
        actor: User,
        project_id: str,
        task_id: str,
        payload: ProjectTaskUpdate,
    ) -> tuple[ProjectTask, User | None]:
        project = await self._get_owned_project_or_404(user_id, project_id)
        task = await self.repo.get_task_by_id(project.id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        fields_set = payload.model_fields_set
        previous_status = task.status
        previous_due_date = task.due_date
        previous_assignee_id = task.assignee_id

        if "title" in fields_set:
            task.title = payload.title or task.title
        if "description" in fields_set:
            task.description = payload.description
        if "priority" in fields_set and payload.priority is not None:
            task.priority = payload.priority
        if "due_date" in fields_set:
            task.due_date = payload.due_date

        assignee = None
        if "assignee_id" in fields_set:
            assignee = await self._get_assignee_or_404(project, payload.assignee_id)
            task.assignee_id = assignee.id if assignee else None
        elif task.assignee_id:
            assignee = await self.users_repo.get_active_user_by_id(task.assignee_id)

        if "status" in fields_set and payload.status is not None and payload.status != task.status:
            task.status = payload.status
            task.position = await self.repo.get_next_task_position(project.id, payload.status)

        await self._notify_assignment(project, task, actor, previous_assignee_id, assignee)
        await self._notify_due_date_change(project, task, actor, previous_due_date, assignee)
        await self._notify_status_change(project, task, actor, previous_status)

        await self.db.commit()
        task_row = await self.repo.get_task_with_assignee(project.id, task.id)
        if not task_row:
            raise HTTPException(status_code=500, detail="Failed to load updated task")
        if "assignee_id" in fields_set and previous_assignee_id != task.assignee_id:
            await self._invalidate_assignment_access_caches(
                project=project,
                previous_assignee_id=previous_assignee_id,
                new_assignee_id=task.assignee_id,
            )
        if "due_date" in fields_set or task.due_date is not None or previous_due_date is not None:
            await invalidate_calendar_cache(user_id)
            if assignee and assignee.id != user_id:
                await invalidate_calendar_cache(assignee.id)
            if (
                previous_assignee_id
                and previous_assignee_id != user_id
                and previous_assignee_id != (assignee.id if assignee else None)
            ):
                await invalidate_calendar_cache(previous_assignee_id)
        return task_row

    async def delete_task(self, user_id: str, project_id: str, task_id: str) -> None:
        project = await self._get_owned_project_or_404(user_id, project_id)
        task = await self.repo.get_task_by_id(project.id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        await self.repo.delete_task(task)
        previous_assignee_id = task.assignee_id
        previous_due_date = task.due_date
        await self.db.commit()
        await self._invalidate_assignment_access_caches(
            project=project,
            previous_assignee_id=previous_assignee_id,
            new_assignee_id=None,
        )
        if previous_due_date is not None:
            await invalidate_calendar_cache(user_id)
            if previous_assignee_id and previous_assignee_id != user_id:
                await invalidate_calendar_cache(previous_assignee_id)

    async def reorder_tasks(
        self,
        user_id: str,
        actor: User,
        project_id: str,
        payload: ProjectTaskReorderRequest,
    ) -> list[tuple[ProjectTask, User | None]]:
        project = await self._get_owned_project_or_404(user_id, project_id)
        task_rows, _ = await self.repo.list_tasks_with_assignees(project.id, limit=MAX_PAGE_LIMIT)
        tasks_by_id = {task.id: task for task, _ in task_rows}
        previous_status_by_id = {task.id: task.status for task, _ in task_rows}

        seen_ids: list[str] = []
        for column in payload.columns:
            for position, task_id in enumerate(column.task_ids):
                task = tasks_by_id.get(task_id)
                if not task:
                    raise HTTPException(status_code=404, detail="Task not found in reorder payload")
                task.status = column.status
                task.position = (position + 1) * TASK_POSITION_GAP
                seen_ids.append(task_id)

        if len(seen_ids) != len(tasks_by_id) or set(seen_ids) != set(tasks_by_id):
            raise HTTPException(
                status_code=400,
                detail="Reorder payload must include every task exactly once",
            )

        await asyncio.gather(
            *[
                self._notify_status_change(project, task, actor, previous_status_by_id[task.id])
                for task, _ in task_rows
            ]
        )

        await self.db.commit()
        rows, _ = await self.repo.list_tasks_with_assignees(project.id, limit=MAX_PAGE_LIMIT)
        return rows

    async def _invalidate_assignment_access_caches(
        self,
        *,
        project: Project,
        previous_assignee_id: str | None,
        new_assignee_id: str | None,
    ) -> None:
        """Drop list and retrieval caches when assignment changes project access.

        Ownership already grants list visibility, so only assignee identities are
        list-invalidated. Shared RAG retrieval is keyed by organization/project
        corpus generation so every member loses stale entries after commit.
        """
        affected = {
            user_id
            for user_id in (previous_assignee_id, new_assignee_id)
            if user_id
        }
        for user_id in sorted(affected):
            await invalidate_project_list_cache(user_id)
        if not affected:
            return
        organization_id = project.organization_id
        if organization_id:
            await bump_corpus_generation(
                organization_id=organization_id,
                project_id=project.id,
            )

    async def _get_project_or_404(self, user_id: str, project_id: str) -> Project:
        project = await self.repo.get_by_id_for_user(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    async def _get_owned_project_or_404(self, user_id: str, project_id: str) -> Project:
        project = await self.repo.get_by_id_for_owner(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    async def _get_assignee_or_404(
        self,
        project: Project,
        assignee_id: str | None,
    ) -> User | None:
        if not assignee_id:
            return None
        organization_id = project.organization_id
        assignee = None
        if organization_id:
            assignee = await self.users_repo.get_active_user_in_organization(
                assignee_id,
                organization_id,
            )
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found")
        return assignee

    async def _notify_assignment(
        self,
        project: Project,
        task: ProjectTask,
        actor: User,
        previous_assignee_id: str | None,
        assignee: User | None,
    ) -> None:
        if not assignee or assignee.id == previous_assignee_id or assignee.id == actor.id:
            return

        await self.notifications_repo.create(
            user_id=assignee.id,
            type="task_assigned",
            title=f"Task assigned: {task.title}",
            body=(
                f"{self._actor_label(actor)} assigned you the task "
                f'"{task.title}" in project "{project.name}".'
            ),
        )

    async def _notify_due_date_change(
        self,
        project: Project,
        task: ProjectTask,
        actor: User,
        previous_due_date: date | None,
        assignee: User | None,
    ) -> None:
        if (
            not assignee
            or assignee.id == actor.id
            or task.due_date is None
            or task.due_date == previous_due_date
        ):
            return

        await self.notifications_repo.create(
            user_id=assignee.id,
            type="task_due_date_updated",
            title=f"Due date updated: {task.title}",
            body=(
                f'{self._actor_label(actor)} set the due date for "{task.title}" '
                f'to {task.due_date.isoformat()} in project "{project.name}".'
            ),
        )

    async def _notify_status_change(
        self,
        project: Project,
        task: ProjectTask,
        actor: User,
        previous_status: str,
    ) -> None:
        if task.status == previous_status or project.owner_id == actor.id:
            return

        if task.status not in {"review", "done"}:
            return

        target_label = "review" if task.status == "review" else "done"
        await self.notifications_repo.create(
            user_id=project.owner_id,
            type="task_status_changed",
            title=f"Task moved to {target_label}: {task.title}",
            body=(
                f'{self._actor_label(actor)} moved "{task.title}" to {target_label} '
                f'in project "{project.name}".'
            ),
        )

    @staticmethod
    def _actor_label(actor: User) -> str:
        return actor.full_name or actor.email
