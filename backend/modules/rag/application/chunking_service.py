from __future__ import annotations

import asyncio

from backend.core.config import settings
from backend.lib.vectors import estimate_tokens
from backend.modules.rag.domain.models import DocumentChunk, ParsedDocument
from backend.modules.rag.infrastructure.langchain_text_splitters import split_documents
from backend.modules.rag.infrastructure.rag_config import RagConfig
from fastapi import HTTPException


def _split_documents_with_token_counts(
    documents: list[ParsedDocument],
    *,
    chunk_size: int,
    chunk_overlap: int,
    tokenizer_model: str | None = None,
) -> list[tuple[str, int, dict]]:
    return [
        (content, estimate_tokens(content, model=tokenizer_model), meta)
        for content, meta in split_documents(
            documents,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer_model=tokenizer_model,
        )
    ]


class ChunkingService:
    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig.from_settings()

    async def chunk(
        self,
        documents: list[ParsedDocument],
        *,
        document_id: str,
        user_id: str,
        filename: str,
        project_id: str | None = None,
        organization_id: str | None = None,
    ) -> list[DocumentChunk]:
        pieces = await asyncio.to_thread(
            _split_documents_with_token_counts,
            documents,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            tokenizer_model=getattr(self.config, "embedding_model", None),
        )
        chunks: list[DocumentChunk] = []
        total_chunks = len(pieces)
        if total_chunks > settings.RAG_MAX_DOCUMENT_CHUNKS:
            raise HTTPException(
                status_code=413,
                detail="Document produces more chunks than the configured limit.",
            )
        previous_content = ""
        for index, (content, token_count, meta) in enumerate(pieces):
            overlap_chars = 0
            if previous_content and content:
                max_overlap = min(len(previous_content), len(content))
                for size in range(max_overlap, 0, -1):
                    if previous_content[-size:] == content[:size]:
                        overlap_chars = size
                        break
            chunks.append(
                DocumentChunk(
                    document_id=document_id,
                    user_id=user_id,
                    chunk_index=index,
                    content=content,
                    token_count=token_count,
                    organization_id=organization_id,
                    project_id=project_id,
                    metadata={
                        "document_id": document_id,
                        "user_id": user_id,
                        "organization_id": organization_id,
                        "project_id": project_id,
                        "filename": filename,
                        "chunk_index": index,
                        "chunk_count": total_chunks,
                        "chunk_char_count": len(content),
                        "chunk_token_count": token_count,
                        "format": meta.get("format", "unknown"),
                        "section_heading": meta.get("section_heading"),
                        "overlap_char_count": overlap_chars,
                        "source_metadata": dict(meta),
                        "page_number": meta.get("page_number"),
                        "source_type": "upload",
                        **meta,
                    },
                )
            )
            previous_content = content
        return chunks
