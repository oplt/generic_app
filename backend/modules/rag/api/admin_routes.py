"""Admin routes for RAG index version status and stale reindex."""

from __future__ import annotations

from backend.api.deps.db import get_db
from backend.lib.idempotency import Idempotency, IdempotencySession
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
    building = summary.get("building_version")
    return RagIndexStatusResponse(
        active_version=_version_response(active),
        desired_index_version=summary.get("desired_index_version"),  # type: ignore[arg-type]
        building_version=_version_response(building) if building is not None else None,
        building_readiness=summary.get("building_readiness"),  # type: ignore[arg-type]
        pipeline=summary["pipeline"],  # type: ignore[arg-type]
        schema_embedding_dimensions=summary["schema_embedding_dimensions"],  # type: ignore[arg-type]
        documents_total=summary["documents_total"],  # type: ignore[arg-type]
        documents_indexed=summary["documents_indexed"],  # type: ignore[arg-type]
        documents_current=summary["documents_current"],  # type: ignore[arg-type]
        documents_stale=summary["documents_stale"],  # type: ignore[arg-type]
        documents_incomplete=summary["documents_incomplete"],  # type: ignore[arg-type]
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
    idem: IdempotencySession = Depends(Idempotency("rag.index_version.create", required=False)),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)

    async def _create() -> RagIndexVersionResponse:
        row = await service.create_building_version(notes=payload.notes)
        await db.commit()
        await db.refresh(row)
        return _version_response(row)

    return await idem.execute(
        _create,
        status_code=201,
        dump=lambda response: response.model_dump(mode="json"),
    )


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
    idem: IdempotencySession = Depends(Idempotency("rag.index_version.activate", required=False)),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)

    async def _activate() -> RagIndexVersionResponse:
        row = await service.activate(version_id)
        await db.commit()
        await db.refresh(row)
        return _version_response(row)

    return await idem.execute(
        _activate,
        status_code=200,
        dump=lambda response: response.model_dump(mode="json"),
    )


@router.post("/index-versions/{version_id}/rollback", response_model=RagIndexVersionResponse)
async def rollback_index_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
    idem: IdempotencySession = Depends(Idempotency("rag.index_version.rollback", required=False)),
):
    require_rag_enabled()
    _ = current_user
    service = IndexVersionService(db)

    async def _rollback() -> RagIndexVersionResponse:
        row = await service.rollback(version_id)
        await db.commit()
        await db.refresh(row)
        return _version_response(row)

    return await idem.execute(
        _rollback,
        status_code=200,
        dump=lambda response: response.model_dump(mode="json"),
    )


@router.post("/reindex-stale", response_model=RagIndexReindexStaleResponse)
async def reindex_stale_documents(
    payload: RagIndexReindexStaleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
    idem: IdempotencySession = Depends(Idempotency("rag.reindex_stale", required=False)),
):
    require_rag_enabled()
    service = IndexVersionService(db)

    async def _reindex() -> RagIndexReindexStaleResponse:
        result = await service.enqueue_stale_reindex(
            actor_user_id=current_user.id,
            limit=payload.limit,
        )
        return RagIndexReindexStaleResponse.model_validate(result)

    return await idem.execute(
        _reindex,
        status_code=200,
        dump=lambda response: response.model_dump(mode="json"),
    )
