from __future__ import annotations

import logging
from time import perf_counter

from backend.modules.rag.application.embedding_service import EmbeddingService
from backend.modules.rag.domain.models import RetrievedChunk
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.vector_store_adapter import build_vector_store
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()
        self.vector_store = build_vector_store(db, self.config)
        self.embeddings = EmbeddingService(self.config)

    async def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        if not self.config.enabled:
            return []

        resolved_top_k = top_k or self.config.top_k
        started = perf_counter()
        try:
            query_embedding = (await self.embeddings.embed_texts([query]))[0]
            results = await self.vector_store.similarity_search(
                query,
                user_id=user_id,
                project_id=project_id,
                top_k=resolved_top_k,
                filters=filters,
                query_embedding=query_embedding,
            )
            metrics.rag_retrieved_chunks.observe(len(results))
            return results
        except Exception:
            logger.exception("RAG retrieval failed for user=%s", user_id)
            metrics.rag_vector_unavailable_total.inc()
            return []
        finally:
            metrics.rag_retrieval_latency_ms.observe((perf_counter() - started) * 1000)
