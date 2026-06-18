from __future__ import annotations

import math

from backend.modules.rag.domain.models import DocumentChunk, ParsedDocument
from backend.modules.rag.infrastructure.langchain_text_splitters import split_documents
from backend.modules.rag.infrastructure.rag_config import RagConfig


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


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
        pieces = split_documents(
            documents,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        chunks: list[DocumentChunk] = []
        for index, (content, meta) in enumerate(pieces):
            chunks.append(
                DocumentChunk(
                    document_id=document_id,
                    user_id=user_id,
                    chunk_index=index,
                    content=content,
                    token_count=_estimate_tokens(content),
                    organization_id=organization_id,
                    project_id=project_id,
                    metadata={
                        "document_id": document_id,
                        "user_id": user_id,
                        "organization_id": organization_id,
                        "project_id": project_id,
                        "filename": filename,
                        "chunk_index": index,
                        "page_number": meta.get("page_number"),
                        "source_type": "upload",
                        **meta,
                    },
                )
            )
        return chunks
