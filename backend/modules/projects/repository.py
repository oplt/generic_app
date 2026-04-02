from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.modules.projects.models import Project


class ProjectsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, owner_id: str, name: str, description: str | None) -> Project:
        project = Project(owner_id=owner_id, name=name, description=description)
        self.db.add(project)
        await self.db.flush()
        return project

    async def list_by_owner(self, owner_id: str) -> list[Project]:
        result = await self.db.execute(
            select(Project).where(Project.owner_id == owner_id).order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())