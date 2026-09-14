from datetime import date

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.core.pagination import (
    DEFAULT_PAGE_LIMIT,
    paginate_cursor_rows,
    paginate_cursor_scalars,
)
from backend.modules.identity_access.models import OrganizationMembership, User
from backend.modules.projects.models import Project, ProjectTask

TASK_POSITION_GAP = 1000


def _project_access_filter(user_id: str):
    user_membership = aliased(OrganizationMembership)
    shares_project_organization = exists(
        select(user_membership.id).where(
            user_membership.user_id == user_id,
            user_membership.organization_id == Project.organization_id,
        )
    )
    return or_(
        Project.owner_id == user_id,
        and_(
            ProjectTask.assignee_id == user_id,
            shares_project_organization,
        ),
    )


class ProjectsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        owner_id: str,
        name: str,
        description: str | None,
        *,
        organization_id: str,
    ) -> Project:
        project = Project(
            owner_id=owner_id,
            organization_id=organization_id,
            name=name,
            description=description,
        )
        self.db.add(project)
        await self.db.flush()
        return project

    async def summary_for_user(self, user_id: str) -> tuple[int, int]:
        access_filter = _project_access_filter(user_id)
        project_count, open_task_count = (
            await self.db.execute(
                select(
                    func.count(Project.id.distinct()),
                    func.count(ProjectTask.id).filter(ProjectTask.status != "done"),
                )
                .select_from(Project)
                .outerjoin(ProjectTask, ProjectTask.project_id == Project.id)
                .where(access_filter)
            )
        ).one()
        return int(project_count or 0), int(open_task_count or 0)

    async def list_accessible_by_user(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        access_filter = _project_access_filter(user_id)
        id_stmt = (
            select(Project.id)
            .outerjoin(ProjectTask, ProjectTask.project_id == Project.id)
            .where(access_filter)
            .distinct()
        )
        total = int(await self.db.scalar(select(func.count()).select_from(id_stmt.subquery())) or 0)
        result = await self.db.execute(
            select(Project)
            .outerjoin(ProjectTask, ProjectTask.project_id == Project.id)
            .where(access_filter)
            .distinct()
            .order_by(Project.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_accessible_by_user_cursor(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[Project], str | None, bool]:
        access_filter = _project_access_filter(user_id)
        stmt = (
            select(Project)
            .outerjoin(ProjectTask, ProjectTask.project_id == Project.id)
            .where(access_filter)
            .distinct()
        )
        return await paginate_cursor_scalars(
            self.db,
            stmt,
            limit=limit,
            cursor=cursor,
            sort_column=Project.created_at,
            id_column=Project.id,
        )

    async def get_by_id_for_user(self, project_id: str, user_id: str) -> Project | None:
        result = await self.db.execute(
            select(Project)
            .outerjoin(ProjectTask, ProjectTask.project_id == Project.id)
            .where(
                Project.id == project_id,
                _project_access_filter(user_id),
            )
            .distinct()
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_owner(self, project_id: str, owner_id: str) -> Project | None:
        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def filter_accessible_project_ids(
        self,
        user_id: str,
        project_ids: set[str],
    ) -> set[str]:
        if not project_ids:
            return set()
        result = await self.db.execute(
            select(Project.id)
            .outerjoin(ProjectTask, ProjectTask.project_id == Project.id)
            .where(
                Project.id.in_(project_ids),
                _project_access_filter(user_id),
            )
            .distinct()
        )
        return set(result.scalars().all())

    async def get_task_by_id(self, project_id: str, task_id: str) -> ProjectTask | None:
        result = await self.db.execute(
            select(ProjectTask).where(
                ProjectTask.id == task_id,
                ProjectTask.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_tasks_with_assignees(
        self,
        project_id: str,
        *,
        limit: int | None = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[tuple[ProjectTask, User | None]], int]:
        assignee = aliased(User)
        status_order = case(
            (ProjectTask.status == "backlog", 0),
            (ProjectTask.status == "todo", 1),
            (ProjectTask.status == "in_progress", 2),
            (ProjectTask.status == "review", 3),
            (ProjectTask.status == "done", 4),
            else_=99,
        )
        total = int(
            await self.db.scalar(
                select(func.count())
                .select_from(ProjectTask)
                .where(ProjectTask.project_id == project_id)
            )
            or 0
        )
        stmt = (
            select(ProjectTask, assignee)
            .outerjoin(assignee, ProjectTask.assignee_id == assignee.id)
            .where(ProjectTask.project_id == project_id)
            .order_by(status_order, ProjectTask.position.asc(), ProjectTask.created_at.asc())
        )
        if limit is not None:
            stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.all()), total

    async def list_tasks_with_assignees_cursor(
        self, project_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[tuple[ProjectTask, User | None]], str | None, bool]:
        assignee = aliased(User)
        stmt = (
            select(ProjectTask, assignee)
            .outerjoin(assignee, ProjectTask.assignee_id == assignee.id)
            .where(ProjectTask.project_id == project_id)
        )
        return await paginate_cursor_rows(
            self.db,
            stmt,
            limit=limit,
            cursor=cursor,
            sort_column=ProjectTask.created_at,
            id_column=ProjectTask.id,
        )

    async def get_task_with_assignee(
        self,
        project_id: str,
        task_id: str,
    ) -> tuple[ProjectTask, User | None] | None:
        assignee = aliased(User)
        result = await self.db.execute(
            select(ProjectTask, assignee)
            .outerjoin(assignee, ProjectTask.assignee_id == assignee.id)
            .where(
                ProjectTask.project_id == project_id,
                ProjectTask.id == task_id,
            )
        )
        return result.first()

    async def get_next_task_position(self, project_id: str, status: str) -> int:
        max_position = await self.db.scalar(
            select(func.max(ProjectTask.position)).where(
                ProjectTask.project_id == project_id,
                ProjectTask.status == status,
            )
        )
        return int(max_position or 0) + TASK_POSITION_GAP

    async def create_task(
        self,
        project_id: str,
        title: str,
        description: str | None,
        status: str,
        priority: str,
        due_date,
        assignee_id: str | None,
        position: int,
    ) -> ProjectTask:
        task = ProjectTask(
            project_id=project_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_date=due_date,
            assignee_id=assignee_id,
            position=position,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def delete_task(self, task: ProjectTask) -> None:
        await self.db.delete(task)
        await self.db.flush()

    async def list_tasks_due_for_user(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[tuple[ProjectTask, Project]]:
        result = await self.db.execute(
            select(ProjectTask, Project)
            .join(Project, ProjectTask.project_id == Project.id)
            .where(
                ProjectTask.due_date.is_not(None),
                ProjectTask.due_date >= start_date,
                ProjectTask.due_date <= end_date,
                _project_access_filter(user_id),
            )
            .order_by(
                ProjectTask.due_date.asc(),
                ProjectTask.position.asc(),
                ProjectTask.created_at.asc(),
            )
        )
        return list(result.all())
