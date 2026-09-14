"""Admin operational jobs console routes."""

from __future__ import annotations

from datetime import datetime

from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.jobs.schemas import (
    JobConsoleItemResponse,
    JobsConsoleListResponse,
)
from backend.modules.jobs.service import JobsConsoleService
from backend.modules.policy.deps import require_permission
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobsConsoleListResponse)
async def list_console_jobs(
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    queue: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    failed_only: bool = Query(default=False),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("jobs.read")),
):
    _ = current_user
    service = JobsConsoleService(db)
    items, total = await service.list_jobs(
        status=status,
        job_type=job_type,
        queue=queue,
        project_id=project_id,
        failed_only=failed_only,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return JobsConsoleListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobConsoleItemResponse)
async def get_console_job(
    job_id: str,
    source: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("jobs.read")),
):
    _ = current_user
    service = JobsConsoleService(db)
    return await service.get_job(job_id, source=source)


@router.post("/{job_id}/retry", response_model=JobConsoleItemResponse)
async def retry_console_job(
    job_id: str,
    source: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("jobs.retry")),
):
    service = JobsConsoleService(db)
    return await service.retry_job(
        job_id,
        actor_id=current_user.id,
        is_admin=bool(current_user.is_admin),
        source=source,
    )


@router.post("/{job_id}/cancel", response_model=JobConsoleItemResponse)
async def cancel_console_job(
    job_id: str,
    source: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("jobs.cancel")),
):
    _ = current_user
    service = JobsConsoleService(db)
    return await service.cancel_job(job_id, source=source)
