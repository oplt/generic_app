"""Shared helpers for RAG HTTP routes."""

from __future__ import annotations

import json

from backend.modules.rag.api.schemas import RagDocumentResponse
from backend.modules.rag.application.document_identity import document_needs_reindex
from backend.modules.rag.infrastructure.rag_config import RagConfig
from fastapi import HTTPException


def require_rag_enabled() -> None:
    if not RagConfig.from_settings().enabled:
        raise HTTPException(status_code=503, detail="RAG is disabled")


def document_to_response(document) -> RagDocumentResponse:
    metadata = json.loads(document.metadata_json or "{}")
    config = RagConfig.from_settings()
    return RagDocumentResponse(
        id=document.id,
        user_id=document.user_id,
        project_id=document.project_id,
        organization_id=document.organization_id,
        filename=document.filename,
        original_filename=document.original_filename,
        content_type=document.content_type,
        fingerprint=getattr(document, "content_fingerprint", None),
        storage_path=document.storage_path,
        status=document.status,
        source_type=document.source_type,
        metadata=metadata,
        created_at=document.created_at,
        updated_at=document.updated_at,
        needs_reindex=(
            document.status == "indexed" and document_needs_reindex(metadata, config)
        ),
    )
