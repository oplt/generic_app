from __future__ import annotations

import asyncio

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    paginated_response,
    pagination_params,
)
from backend.modules.ai.dependencies import enforce_ai_generation_rate_limit
from backend.modules.identity_access.models import User
from backend.modules.rag.api.route_helpers import require_rag_enabled
from backend.modules.rag.api.schemas import (
    RagAskRequest,
    RagAskResponse,
    RagCitationResponse,
    RagQueryResponse,
    RagRetrievedChunkResponse,
    RagRetrieveRequest,
    RagRetrieveResponse,
    RagWebSourceResponse,
)
from backend.modules.rag.application.rag_answer_service import RagAnswerService
from backend.modules.rag.application.retrieval_service import RetrievalService
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.modules.rag.workers import (
    queue_document_indexing,  # noqa: F401 — compatibility patch target
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.post("/retrieve", response_model=RagRetrieveResponse)
async def retrieve_chunks(
    payload: RagRetrieveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    service = RetrievalService(db)
    filters = {
        key: value
        for key, value in {
            "document_ids": payload.document_ids,
            "source_type": payload.source_type,
        }.items()
        if value
    } or None
    outcome = await service.retrieve(
        payload.query,
        user_id=current_user.id,
        project_id=payload.project_id,
        top_k=payload.top_k,
        filters=filters,
        strategy=payload.strategy,
    )
    return RagRetrieveResponse(
        chunks=[
            RagRetrievedChunkResponse(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=chunk.score,
                filename=chunk.filename,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
            )
            for chunk in outcome.chunks
        ],
        degraded=outcome.degraded,
        degradation_reason=outcome.degradation_reason,
        no_matches=outcome.no_matches,
        injection_chunks_filtered=outcome.injection_chunks_filtered,
    )


@router.post("/ask", response_model=RagAskResponse)
async def ask_rag(
    payload: RagAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(enforce_ai_generation_rate_limit),
):
    require_rag_enabled()
    service = RagAnswerService(db)
    try:
        result = await asyncio.wait_for(
            service.answer(
                payload.query,
                user=current_user,
                project_id=payload.project_id,
                run_id=payload.run_id,
                agent_id=payload.agent_id,
                document_ids=payload.document_ids or None,
                mode=payload.mode,
                use_memory=payload.use_memory,
            ),
            timeout=settings.RAG_ASK_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="RAG answer timed out") from exc
    return RagAskResponse(
        query=result.query,
        answer=result.answer,
        citations=[
            RagCitationResponse(
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                filename=c.filename,
                score=c.score,
                snippet=c.snippet,
                page_number=c.page_number,
                chunk_index=c.chunk_index,
            )
            for c in result.citations
        ],
        retrieved_chunk_ids=result.retrieved_chunk_ids,
        model_name=result.model_name,
        latency_ms=result.latency_ms,
        no_context_found=result.no_context_found,
        ai_run_id=result.ai_run_id,
        retrieval_degraded=result.retrieval_degraded,
        memory_degraded=result.memory_degraded,
        degradation_reason=result.degradation_reason,
        injection_chunks_filtered=result.injection_chunks_filtered,
        citation_validated=result.citation_validated,
        needs_review=result.needs_review,
        mode=result.mode,
        web_sources=[
            RagWebSourceResponse(
                source_id=source.source_id,
                title=source.title,
                url=source.url,
                snippet=source.snippet,
                rank=source.rank,
                published_at=source.published_at,
            )
            for source in result.web_citations
        ],
    )


@router.get("/queries", response_model=PaginatedResponse[RagQueryResponse])
async def list_queries(
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    repo = RagRepository(db)
    next_cursor = None
    has_more = False
    if getattr(pagination, "cursor", None):
        rows, next_cursor, has_more = await repo.list_queries_for_user_cursor(
            current_user.id, limit=pagination.limit, cursor=pagination.cursor
        )
        total = None
    else:
        rows, total = await repo.list_queries_for_user(
            current_user.id, limit=pagination.limit, offset=pagination.offset
        )
    return paginated_response(
        [RagQueryResponse.model_validate(row) for row in rows],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        next_cursor=next_cursor,
        has_more=has_more,
    )


