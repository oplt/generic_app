from __future__ import annotations

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    paginated_response,
    pagination_params,
)
from backend.lib.idempotency import Idempotency, IdempotencySession
from backend.modules.identity_access.models import User
from backend.modules.rag.api.route_helpers import require_rag_enabled
from backend.modules.rag.api.schemas import (
    RagIngestionJobResponse,
)
from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.modules.rag.workers import (
    queue_document_indexing,  # noqa: F401 — compatibility patch target
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.get("/jobs", response_model=PaginatedResponse[RagIngestionJobResponse])
async def list_jobs(
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    repo = RagRepository(db)
    jobs, total = await repo.list_ingestion_jobs_for_user(
        current_user.id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated_response(
        [RagIngestionJobResponse.model_validate(job) for job in jobs],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/jobs/{job_id}", response_model=RagIngestionJobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    repo = RagRepository(db)
    job = await repo.get_ingestion_job(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return RagIngestionJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/retry", response_model=RagIngestionJobResponse, status_code=202)
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idem: IdempotencySession = Depends(Idempotency("rag.ingestion.retry", required=False)),
):
    """Create a fresh durable outbox attempt for a failed/stuck ingestion job."""
    require_rag_enabled()

    async def _retry() -> RagIngestionJobResponse:
        repo = RagRepository(db)
        old_job = await repo.get_ingestion_job(job_id)
        if not old_job or old_job.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Job not found")
        if old_job.status == "completed":
            raise HTTPException(status_code=409, detail="Ingestion job is already complete")
        service = DocumentIngestionService(db)
        job = await service.enqueue_document_indexing(
            document_id=old_job.document_id,
            user_id=current_user.id,
            is_admin=current_user.is_admin,
            force_new_attempt=True,
        )
        return RagIngestionJobResponse.model_validate(job)

    return await idem.execute(
        _retry,
        status_code=202,
        dump=lambda response: response.model_dump(mode="json"),
    )
