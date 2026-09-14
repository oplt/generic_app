from __future__ import annotations

import json

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    paginated_response,
    pagination_params,
)
from backend.core.text_snippet import text_snippet
from backend.core.uploads import UploadTooLargeError, read_upload_limited
from backend.lib.project_access import SqlAlchemyProjectAccessPort
from backend.modules.identity_access.models import User
from backend.modules.policy import authorize, catalog
from backend.modules.rag.api.route_helpers import document_to_response, require_rag_enabled
from backend.modules.rag.api.schemas import (
    RagChunkResponse,
    RagDocumentResponse,
    RagDocumentUploadResponse,
    RagIngestionJobResponse,
)
from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.modules.rag.workers import (
    queue_document_indexing,  # noqa: F401 — compatibility patch target
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.post("/documents/upload", response_model=RagDocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    try:
        content = await read_upload_limited(
            file, max_bytes=RagConfig.from_settings().max_file_bytes
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded document file is empty")
    scope = await SqlAlchemyProjectAccessPort(db).resolve_ownership_scope(
        current_user.id,
        project_id,
    )
    await authorize(
        db=db,
        actor=current_user,
        action=catalog.RAG_MANAGE,
        organization_id=scope.organization_id,
        project_id=scope.project_id,
    )
    service = DocumentIngestionService(db)
    upload_result = await service.upload_document(
        user_id=current_user.id,
        filename=file.filename or "upload.bin",
        content=content,
        content_type=file.content_type or "application/octet-stream",
        project_id=project_id,
    )
    document, job = upload_result
    return RagDocumentUploadResponse(
        document=document_to_response(document),
        ingestion_job=RagIngestionJobResponse.model_validate(job),
        duplicate=upload_result.duplicate,
    )


@router.get("/documents", response_model=PaginatedResponse[RagDocumentResponse])
async def list_documents(
    project_id: str | None = None,
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    repo = RagRepository(db)
    next_cursor = None
    has_more = False
    if getattr(pagination, "cursor", None):
        docs, next_cursor, has_more = await repo.list_documents_for_user_cursor(
            current_user.id, project_id=project_id, limit=pagination.limit, cursor=pagination.cursor
        )
        total = None
    else:
        docs, total = await repo.list_documents_for_user(
            current_user.id, project_id=project_id, limit=pagination.limit, offset=pagination.offset
        )
    return paginated_response(
        [document_to_response(doc) for doc in docs],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/documents/{document_id}", response_model=RagDocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    repo = RagRepository(db)
    document = await repo.get_document(document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_to_response(document)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    service = DocumentIngestionService(db)
    await service.delete_document(
        document_id=document_id,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post(
    "/documents/{document_id}/index",
    response_model=RagIngestionJobResponse,
    status_code=202,
)
async def index_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    service = DocumentIngestionService(db)
    job = await service.enqueue_document_indexing(
        document_id=document_id,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )
    return RagIngestionJobResponse.model_validate(job)


@router.post(
    "/documents/{document_id}/reindex",
    response_model=RagIngestionJobResponse,
    status_code=202,
)
async def reindex_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Semantic alias for indexing, kept for document-chat clients."""
    require_rag_enabled()
    service = DocumentIngestionService(db)
    job = await service.enqueue_document_indexing(
        document_id=document_id,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )
    return RagIngestionJobResponse.model_validate(job)


@router.get(
    "/documents/{document_id}/chunks",
    response_model=PaginatedResponse[RagChunkResponse],
)
async def list_document_chunks(
    document_id: str,
    pagination: PaginationParams = Depends(pagination_params),
    content_mode: str = Query(
        default="snippet",
        pattern="^(snippet|full)$",
        description="Return truncated chunk previews (snippet) or full chunk text (full).",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_rag_enabled()
    repo = RagRepository(db)
    document = await repo.get_document(document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    next_cursor = None
    has_more = False
    if getattr(pagination, "cursor", None):
        chunks, next_cursor, has_more = await repo.list_chunks_for_document_cursor(
            document_id, limit=pagination.limit, cursor=pagination.cursor
        )
        total = None
    else:
        chunks, total = await repo.list_chunks_for_document(
            document_id, limit=pagination.limit, offset=pagination.offset
        )

    def chunk_content(raw: str) -> str:
        if content_mode == "full":
            return raw
        return text_snippet(raw)

    return paginated_response(
        [
            RagChunkResponse(
                id=chunk.id,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                content=chunk_content(chunk.content),
                token_count=chunk.token_count,
                metadata=json.loads(chunk.metadata_json or "{}"),
            )
            for chunk in chunks
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        next_cursor=next_cursor,
        has_more=has_more,
    )


