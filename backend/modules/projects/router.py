from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.projects.schemas import ProjectCreate, ProjectResponse
from backend.modules.projects.service import ProjectsService

router = APIRouter()


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProjectsService(db)
    projects = await service.list_projects(current_user.id)
    return [
        ProjectResponse(id=p.id, name=p.name, description=p.description)
        for p in projects
    ]


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProjectsService(db)
    project = await service.create_project(current_user.id, payload.name, payload.description)
    return ProjectResponse(id=project.id, name=project.name, description=project.description)
