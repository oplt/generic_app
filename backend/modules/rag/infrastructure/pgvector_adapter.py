from __future__ import annotations

import logging

from backend.modules.rag.domain.models import RetrievedChunk
from backend.modules.rag.infrastructure.pgvector_errors import PgVectorUnavailableError
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class VectorStoreAdapter:
    async def similarity_search(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        top_k: int,
        filters: dict | None = None,
        query_embedding: list[float] | None = None,
        organization_id: str | None = None,
    ) -> list[RetrievedChunk]: ...

    async def delete_document(self, document_id: str, user_id: str) -> None: ...


class PgVectorAdapter:
    """
    Postgres pgvector-backed vector store.

    Uses HNSW indexed cosine search. Missing pgvector/schema readiness is surfaced
    as a retrieval failure rather than silently scanning an unindexed JSON column.
    """

    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.repo = RagRepository(db)
        self.config = config or RagConfig.from_settings()

    async def similarity_search(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        top_k: int,
        filters: dict | None = None,
        query_embedding: list[float] | None = None,
        organization_id: str | None = None,
    ) -> list[RetrievedChunk]:
        if query_embedding is None:
            raise PgVectorUnavailableError("query_embedding_missing")

        document_ids = (filters or {}).get("document_ids")
        source_type = (filters or {}).get("source_type")
        indexed = await self.repo.similarity_search_indexed(
            user_id=user_id,
            project_id=project_id,
            document_ids=document_ids,
            source_type=source_type,
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            score_threshold=self.config.score_threshold,
            # RetrievalService owns rerank candidate expansion and passes the
            # already-expanded limit as top_k. Do not multiply again here.
            candidate_limit=top_k,
            organization_id=organization_id,
        )
        if indexed is None:
            raise PgVectorUnavailableError("repository_returned_no_result")

        return indexed

    async def delete_document(self, document_id: str, user_id: str) -> None:
        del user_id
        await self.repo.delete_chunks_for_document(document_id)


def build_vector_store(db: AsyncSession, config: RagConfig | None = None) -> PgVectorAdapter:
    return PgVectorAdapter(db, config)
