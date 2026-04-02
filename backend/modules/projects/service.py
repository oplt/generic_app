from sqlalchemy.ext.asyncio import AsyncSession
from backend.modules.projects.repository import ProjectsRepository


class ProjectsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProjectsRepository(db)

    async def create_project(self, owner_id: str, name: str, description: str | None):
        project = await self.repo.create(owner_id, name, description)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def list_projects(self, owner_id: str):
        return await self.repo.list_by_owner(owner_id)