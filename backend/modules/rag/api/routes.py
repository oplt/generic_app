import json

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.rag.api.schemas import (
    RagAskRequest,
    RagAskResponse,
    RagChunkResponse,
    RagCitationResponse,
    RagDocumentResponse,
    RagIngestionJobResponse,
    RagQueryResponse,
    RagRetrievedChunkResponse,
    RagRetrieveRequest,
)
from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService
from backend.modules.rag.application.rag_answer_service import RagAnswerService
from backend.modules.rag.application.retrieval_service import RetrievalService
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.modules.rag.workers import get_pending_content, queue_document_indexing
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _require_rag_enabled() -> None:
    if not RagConfig.from_settings().enabled:
        raise HTTPException(status_code=503, detail="RAG is disabled")


def _document_to_response(document) -> RagDocumentResponse:
    return RagDocumentResponse(
        id=document.id,
        user_id=document.user_id,
        project_id=document.project_id,
        organization_id=document.organization_id,
        filename=document.filename,
        original_filename=document.original_filename,
        content_type=document.content_type,
        storage_path=document.storage_path,
        status=document.status,
        source_type=document.source_type,
        metadata=json.loads(document.metadata_json or "{}"),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post("/documents/upload", response_model=RagDocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    content = await file.read()
    service = DocumentIngestionService(db)
    document, job, raw_content = await service.upload_document(
        user_id=current_user.id,
        filename=file.filename or "upload.bin",
        content=content,
        content_type=file.content_type or "application/octet-stream",
        project_id=project_id,
    )
    queue_document_indexing(document_id=document.id, user_id=current_user.id, content=raw_content)
    return _document_to_response(document)


@router.get("/documents", response_model=list[RagDocumentResponse])
async def list_documents(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    repo = RagRepository(db)
    docs = await repo.list_documents_for_user(current_user.id, project_id=project_id)
    return [_document_to_response(doc) for doc in docs]


@router.get("/documents/{document_id}", response_model=RagDocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    repo = RagRepository(db)
    document = await repo.get_document(document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return _document_to_response(document)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    service = DocumentIngestionService(db)
    await service.delete_document(
        document_id=document_id,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post(
    "/documents/{document_id}/index",
    response_model=RagIngestionJobResponse,
)
async def index_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    service = DocumentIngestionService(db)
    content = get_pending_content(document_id)
    _document, _chunks, job = await service.index_document(
        document_id=document_id,
        user_id=current_user.id,
        file_content=content,
        is_admin=current_user.is_admin,
    )
    return RagIngestionJobResponse.model_validate(job)


@router.get("/documents/{document_id}/chunks", response_model=list[RagChunkResponse])
async def list_document_chunks(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    repo = RagRepository(db)
    document = await repo.get_document(document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = await repo.list_chunks_for_document(document_id)
    return [
        RagChunkResponse(
            id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            token_count=chunk.token_count,
            metadata=json.loads(chunk.metadata_json or "{}"),
        )
        for chunk in chunks
    ]


@router.post("/retrieve", response_model=list[RagRetrievedChunkResponse])
async def retrieve_chunks(
    payload: RagRetrieveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    service = RetrievalService(db)
    filters = {"document_ids": payload.document_ids} if payload.document_ids else None
    chunks = await service.retrieve(
        payload.query,
        user_id=current_user.id,
        project_id=payload.project_id,
        top_k=payload.top_k,
        filters=filters,
    )
    return [
        RagRetrievedChunkResponse(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            content=chunk.content,
            score=chunk.score,
            filename=chunk.filename,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
        )
        for chunk in chunks
    ]


@router.post("/ask", response_model=RagAskResponse)
async def ask_rag(
    payload: RagAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    service = RagAnswerService(db)
    result = await service.answer(
        payload.query,
        user_id=current_user.id,
        project_id=payload.project_id,
        run_id=payload.run_id,
        agent_id=payload.agent_id,
        document_ids=payload.document_ids or None,
    )
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
    )


@router.get("/queries", response_model=list[RagQueryResponse])
async def list_queries(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    repo = RagRepository(db)
    rows = await repo.list_queries_for_user(current_user.id, limit=limit)
    return [RagQueryResponse.model_validate(row) for row in rows]


@router.get("/jobs/{job_id}", response_model=RagIngestionJobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_rag_enabled()
    repo = RagRepository(db)
    job = await repo.get_ingestion_job(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return RagIngestionJobResponse.model_validate(job)
