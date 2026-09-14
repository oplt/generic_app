"""Admin routes for RAG index version status and stale reindex."""

from __future__ import annotations

from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.policy.deps import require_permission
from backend.modules.rag.api.route_helpers import require_rag_enabled
from backend.modules.rag.api.schemas import (
    RagIndexReindexStaleRequest,
    RagIndexReindexStaleResponse,
    RagIndexStatusResponse,
    RagIndexVersionCreateRequest,
    RagIndexVersionResponse,
)
from backend.modules.rag.application.index_version_service import IndexVersionService
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin")


def _version_response(row) -> RagIndexVersionResponse:
    return RagIndexVersionResponse.model_validate(row)


@router.get("/index-status", response_model=RagIndexStatusResponse)
async def get_index_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)
    summary = await service.status_summary()
    await db.commit()
    active = summary["active_version"]
    return RagIndexStatusResponse(
        active_version=_version_response(active),
        pipeline=summary["pipeline"],  # type: ignore[arg-type]
        schema_embedding_dimensions=summary["schema_embedding_dimensions"],  # type: ignore[arg-type]
        documents_total=summary["documents_total"],  # type: ignore[arg-type]
        documents_indexed=summary["documents_indexed"],  # type: ignore[arg-type]
        documents_current=summary["documents_current"],  # type: ignore[arg-type]
        documents_stale=summary["documents_stale"],  # type: ignore[arg-type]
        jobs_active=summary["jobs_active"],  # type: ignore[arg-type]
        jobs_failed=summary["jobs_failed"],  # type: ignore[arg-type]
        dimension_migration_required=summary["dimension_migration_required"],  # type: ignore[arg-type]
        versions=[_version_response(item) for item in summary["versions"]],  # type: ignore[arg-type]
    )


@router.get("/index-versions", response_model=list[RagIndexVersionResponse])
async def list_index_versions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)
    await service.ensure_active_version()
    versions = await service.list_versions()
    await db.commit()
    return [_version_response(item) for item in versions]


@router.post("/index-versions", response_model=RagIndexVersionResponse, status_code=201)
async def create_index_version(
    payload: RagIndexVersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)
    row = await service.create_building_version(notes=payload.notes)
    await db.commit()
    await db.refresh(row)
    return _version_response(row)


@router.post("/index-versions/{version_id}/validate", response_model=RagIndexVersionResponse)
async def validate_index_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)
    row = await service.mark_validated(version_id)
    await db.commit()
    await db.refresh(row)
    return _version_response(row)


@router.post("/index-versions/{version_id}/activate", response_model=RagIndexVersionResponse)
async def activate_index_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)
    row = await service.activate(version_id)
    await db.commit()
    await db.refresh(row)
    return _version_response(row)


@router.post("/reindex-stale", response_model=RagIndexReindexStaleResponse)
async def reindex_stale_documents(
    payload: RagIndexReindexStaleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = IndexVersionService(db)
    result = await service.enqueue_stale_reindex(
        actor_user_id=current_user.id,
        limit=payload.limit,
    )
    return RagIndexReindexStaleResponse.model_validate(result)
