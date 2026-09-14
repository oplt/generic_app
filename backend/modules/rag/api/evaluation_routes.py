"""Admin routes for the RAG evaluation workbench."""

from __future__ import annotations

from typing import Any

from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.policy.deps import require_permission
from backend.modules.rag.api.route_helpers import require_rag_enabled
from backend.modules.rag.api.schemas import (
    RagEvalCaseCreateRequest,
    RagEvalCaseResponse,
    RagEvalDatasetCreateRequest,
    RagEvalDatasetResponse,
    RagEvalProbeRequest,
    RagEvalRunItemResponse,
    RagEvalRunRequest,
    RagEvalRunResponse,
)
from backend.modules.rag.application.evaluation_service import RagEvaluationService
from backend.modules.rag.infrastructure.models import (
    RagEvaluationCase,
    RagEvaluationDataset,
    RagEvaluationRun,
    RagEvaluationRunItem,
)
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/evaluation")


def _dataset_response(row: RagEvaluationDataset) -> RagEvalDatasetResponse:
    return RagEvalDatasetResponse(
        id=row.id,
        user_id=row.user_id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        tags=list(row.tags_json or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _case_response(row: RagEvaluationCase) -> RagEvalCaseResponse:
    return RagEvalCaseResponse(
        id=row.id,
        dataset_id=row.dataset_id,
        question=row.question,
        expected_document_ids=list(row.expected_document_ids_json or []),
        expected_chunk_ids=list(row.expected_chunk_ids_json or []),
        expected_sources=list(row.expected_sources_json or []),
        expected_facts=list(row.expected_facts_json or []),
        judgments={str(k): int(v) for k, v in (row.judgments_json or {}).items()},
        tags=list(row.tags_json or []),
        notes=row.notes,
        created_at=row.created_at,
    )


def _run_item_response(row: RagEvaluationRunItem) -> RagEvalRunItemResponse:
    return RagEvalRunItemResponse(
        id=row.id,
        case_id=row.case_id,
        ranked_chunk_ids=list(row.ranked_chunk_ids_json or []),
        candidates=list(row.candidates_json or []),
        metrics=dict(row.metrics_json or {}),
        latency=dict(row.latency_json or {}),
        included_in_context=bool(row.included_in_context),
        score=float(row.score or 0.0),
        notes=row.notes,
    )


def _run_response(
    row: RagEvaluationRun, items: list[RagEvaluationRunItem] | None = None
) -> RagEvalRunResponse:
    return RagEvalRunResponse(
        id=row.id,
        dataset_id=row.dataset_id,
        user_id=row.user_id,
        organization_id=row.organization_id,
        name=row.name,
        status=row.status,
        configuration=dict(row.configuration_json or {}),
        metrics=dict(row.metrics_json or {}),
        latency=dict(row.latency_json or {}),
        baseline_run_id=row.baseline_run_id,
        comparison=row.comparison_json,
        error_message=row.error_message,
        created_at=row.created_at,
        completed_at=row.completed_at,
        items=[_run_item_response(item) for item in (items or [])],
    )


def _tenant_org(current_user: User, organization_id: str | None) -> str | None:
    if organization_id:
        return organization_id
    return None


@router.get("/datasets", response_model=list[RagEvalDatasetResponse])
async def list_datasets(
    organization_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    rows, _ = await service.list_datasets(
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, organization_id),
    )
    return [_dataset_response(row) for row in rows]


@router.post("/datasets", response_model=RagEvalDatasetResponse, status_code=201)
async def create_dataset(
    payload: RagEvalDatasetCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    row = await service.create_dataset(
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, payload.organization_id),
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
    )
    await db.commit()
    await db.refresh(row)
    return _dataset_response(row)


@router.post("/datasets/import-golden", response_model=RagEvalDatasetResponse, status_code=201)
async def import_golden_dataset(
    organization_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    row = await service.import_golden_dataset(
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, organization_id),
    )
    await db.commit()
    await db.refresh(row)
    return _dataset_response(row)


@router.get("/datasets/{dataset_id}/cases", response_model=list[RagEvalCaseResponse])
async def list_cases(
    dataset_id: str,
    organization_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    rows = await service.list_cases(
        dataset_id,
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, organization_id),
    )
    return [_case_response(row) for row in rows]


@router.post(
    "/datasets/{dataset_id}/cases",
    response_model=RagEvalCaseResponse,
    status_code=201,
)
async def create_case(
    dataset_id: str,
    payload: RagEvalCaseCreateRequest,
    organization_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    row = await service.create_case(
        dataset_id,
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, organization_id),
        question=payload.question,
        expected_document_ids=payload.expected_document_ids,
        expected_chunk_ids=payload.expected_chunk_ids,
        expected_sources=payload.expected_sources,
        expected_facts=payload.expected_facts,
        judgments=payload.judgments,
        tags=payload.tags,
        notes=payload.notes,
    )
    await db.commit()
    await db.refresh(row)
    return _case_response(row)


@router.post("/probe")
async def probe_retrieval(
    payload: RagEvalProbeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
) -> dict[str, Any]:
    require_rag_enabled()
    service = RagEvaluationService(db)
    return await service.probe(
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, payload.organization_id),
        query=payload.query,
        project_id=payload.project_id,
        document_ids=payload.document_ids,
        strategy=payload.strategy,
        top_k=payload.top_k,
        include_generation_judges=payload.include_generation_judges,
    )


@router.post(
    "/datasets/{dataset_id}/runs",
    response_model=RagEvalRunResponse,
    status_code=201,
)
async def run_dataset(
    dataset_id: str,
    payload: RagEvalRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    run = await service.run_dataset(
        dataset_id,
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, payload.organization_id),
        name=payload.name,
        project_id=payload.project_id,
        strategy=payload.strategy,
        top_k=payload.top_k,
        baseline_run_id=payload.baseline_run_id,
        include_generation_judges=payload.include_generation_judges,
    )
    items = await service.repo.list_run_items(run.id)
    await db.commit()
    return _run_response(run, items)


@router.get("/runs", response_model=list[RagEvalRunResponse])
async def list_runs(
    dataset_id: str | None = Query(default=None),
    organization_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    rows, _ = await service.list_runs(
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, organization_id),
        dataset_id=dataset_id,
    )
    return [_run_response(row) for row in rows]


@router.get("/runs/{run_id}", response_model=RagEvalRunResponse)
async def get_run(
    run_id: str,
    organization_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    run, items = await service.get_run(
        run_id,
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, organization_id),
    )
    return _run_response(run, items)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    export_format: str = Query(default="json", alias="format", pattern="^(json|csv)$"),
    organization_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag.manage")),
):
    require_rag_enabled()
    service = RagEvaluationService(db)
    body, media_type, filename = await service.export_run(
        run_id,
        user_id=current_user.id,
        organization_id=_tenant_org(current_user, organization_id),
        fmt=export_format,
    )
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
