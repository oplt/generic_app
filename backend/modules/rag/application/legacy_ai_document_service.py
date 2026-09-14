from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.core.pagination import DEFAULT_PAGE_LIMIT
from backend.core.uploads import UploadTooLargeError, read_upload_limited
from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService
from backend.modules.rag.application.retrieval_service import RetrievalService
from backend.modules.rag.domain.enums import DocumentStatus
from backend.modules.rag.infrastructure.models import RagDocument
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

_SAFE_FILENAME = re.compile(r"[^\w.\-]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class AiDocumentView:
    """Legacy /api/v1/ai/documents response shape backed by rag_documents."""

    id: str
    title: str
    description: str | None
    filename: str | None
    content_type: str
    size_bytes: int
    ingestion_status: str
    metadata_json: dict[str, Any]
    chunk_count: int
    created_at: datetime
    updated_at: datetime


def _map_ingestion_status(rag_status: str) -> str:
    if rag_status == DocumentStatus.INDEXED.value:
        return "completed"
    if rag_status == DocumentStatus.FAILED.value:
        return "failed"
    if rag_status in {
        DocumentStatus.VALIDATING.value,
        DocumentStatus.EXTRACTING.value,
        DocumentStatus.PARSING.value,
        DocumentStatus.CHUNKING.value,
        DocumentStatus.EMBEDDING.value,
    }:
        return "processing"
    return "pending"


def _safe_stem(title: str) -> str:
    stem = _SAFE_FILENAME.sub("_", title.strip()) or "document"
    return stem[:200]


def _filename_for_text(title: str, content_type: str) -> str:
    stem = _safe_stem(title)
    if stem.endswith((".txt", ".md", ".csv")):
        return stem
    if content_type == "text/markdown":
        return f"{stem}.md"
    return f"{stem}.txt"


def rag_document_to_ai_view(document: RagDocument) -> AiDocumentView:
    metadata = json.loads(document.metadata_json or "{}")
    title = metadata.get("title") or document.original_filename
    return AiDocumentView(
        id=document.id,
        title=title,
        description=metadata.get("description"),
        filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=int(metadata.get("size_bytes") or 0),
        ingestion_status=_map_ingestion_status(document.status),
        metadata_json=metadata,
        chunk_count=int(metadata.get("chunk_count") or 0),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


class LegacyAiDocumentService:
    """Serves legacy /ai/documents* endpoints through the RAG document pipeline."""

    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()
        self.repo = RagRepository(db)
        self.ingestion = DocumentIngestionService(db, self.config)
        self.retrieval = RetrievalService(db, self.config)

    async def list_documents(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[AiDocumentView], int]:
        documents, total = await self.repo.list_documents_for_user(
            user_id, limit=limit, offset=offset
        )
        return [rag_document_to_ai_view(doc) for doc in documents], total

    async def list_documents_cursor(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[AiDocumentView], str | None, bool]:
        documents, next_cursor, has_more = await self.repo.list_documents_for_user_cursor(
            user_id, project_id=None, limit=limit, cursor=cursor
        )
        return [rag_document_to_ai_view(doc) for doc in documents], next_cursor, has_more

    async def create_from_text(
        self,
        *,
        user_id: str,
        title: str,
        description: str | None,
        content: str,
        content_type: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AiDocumentView:
        payload = content.encode("utf-8")
        resolved_filename = filename or _filename_for_text(title, content_type)
        document, job = await self.ingestion.upload_document(
            user_id=user_id,
            filename=resolved_filename,
            content=payload,
            content_type=content_type,
            metadata={
                **(metadata or {}),
                "title": title,
                "description": description,
                "size_bytes": len(payload),
            },
        )
        return rag_document_to_ai_view(document)

    async def create_from_upload(
        self,
        *,
        user_id: str,
        file: UploadFile,
        description: str | None,
    ) -> AiDocumentView:
        try:
            content = await read_upload_limited(file, max_bytes=self.config.max_file_bytes)
        except UploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded document file is empty")
        title = file.filename or "Untitled document"
        document, job = await self.ingestion.upload_document(
            user_id=user_id,
            filename=file.filename or "upload.bin",
            content=content,
            content_type=file.content_type or "application/octet-stream",
            metadata={
                "title": title,
                "description": description,
                "size_bytes": len(content),
            },
        )
        return rag_document_to_ai_view(document)

    async def retrieve_chunks(
        self,
        *,
        user_id: str,
        query: str,
        document_ids: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        candidate_ids: list[str] | None
        if document_ids:
            allowed = await self.repo.filter_document_ids_for_user(user_id, document_ids)
            if len(allowed) != len(document_ids):
                raise HTTPException(status_code=404, detail="One or more documents were not found")
            candidate_ids = document_ids
        else:
            candidate_ids = None

        filters = {"document_ids": candidate_ids} if candidate_ids else None
        outcome = await self.retrieval.retrieve(
            query,
            user_id=user_id,
            project_id=None,
            top_k=top_k,
            filters=filters,
        )
        return [
            {
                "document_id": match.document_id,
                "chunk_id": match.chunk_id,
                "document_title": match.filename or "Untitled document",
                "chunk_index": match.chunk_index,
                "score": match.score,
                "content": match.content,
            }
            for match in outcome.chunks
        ]
