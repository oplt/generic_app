from __future__ import annotations

import json
import logging
import math
from typing import Protocol

from backend.modules.rag.domain.models import DocumentChunk, RetrievedChunk
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class VectorStoreAdapter(Protocol):
    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None: ...

    async def similarity_search(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        top_k: int,
        filters: dict | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]: ...

    async def delete_document(self, document_id: str, user_id: str) -> None: ...


class PgVectorAdapter:
    """
    Postgres-backed vector store.

    Stores embeddings in rag_chunks.embedding_json and performs filtered cosine search.
    Native pgvector column can be added later without changing application code.
    """

    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.repo = RagRepository(db)
        self.config = config or RagConfig.from_settings()

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        metrics.rag_vector_upsert_success_total.inc()

    async def similarity_search(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        top_k: int,
        filters: dict | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        document_ids = (filters or {}).get("document_ids")
        if document_ids:
            docs = await self.repo.list_indexed_documents(
                user_id, project_id=project_id, document_ids=document_ids
            )
        else:
            docs = await self.repo.list_indexed_documents(user_id, project_id=project_id)

        if not docs:
            return []

        doc_map = {doc.id: doc for doc in docs}
        db_chunks = await self.repo.list_chunks_for_documents(list(doc_map))
        if not db_chunks or query_embedding is None:
            return []

        matches: list[RetrievedChunk] = []
        for chunk in db_chunks:
            if chunk.user_id != user_id:
                continue
            if project_id and chunk.project_id != project_id:
                continue
            embedding = json.loads(chunk.embedding_json or "[]")
            if not embedding:
                continue
            score = _cosine_similarity(query_embedding, embedding)
            if score < self.config.score_threshold:
                continue
            doc = doc_map.get(chunk.document_id)
            meta = json.loads(chunk.metadata_json or "{}")
            matches.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    score=round(score, 4),
                    filename=doc.original_filename if doc else "unknown",
                    chunk_index=chunk.chunk_index,
                    page_number=meta.get("page_number"),
                    metadata=meta,
                )
            )
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:top_k]

    async def delete_document(self, document_id: str, user_id: str) -> None:
        document = await self.repo.get_document(document_id)
        if document and document.user_id == user_id:
            await self.repo.soft_delete_document(document)


class QdrantAdapter:
    """Placeholder for future Qdrant integration."""

    def __init__(self, *_args, **_kwargs):
        self._available = False

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        metrics.rag_vector_unavailable_total.inc()
        raise RuntimeError("Qdrant vector backend is not configured")

    async def similarity_search(self, **kwargs) -> list[RetrievedChunk]:
        metrics.rag_vector_unavailable_total.inc()
        return []

    async def delete_document(self, document_id: str, user_id: str) -> None:
        metrics.rag_vector_unavailable_total.inc()


def build_vector_store(db: AsyncSession, config: RagConfig | None = None) -> VectorStoreAdapter:
    cfg = config or RagConfig.from_settings()
    backend = cfg.vector_backend
    if backend == "qdrant":
        return QdrantAdapter()
    return PgVectorAdapter(db, cfg)
