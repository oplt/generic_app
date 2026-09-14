from __future__ import annotations

import logging
from time import perf_counter

from backend.core.config import settings
from backend.lib.retrieval_cache import get_cached_retrieval, set_cached_retrieval
from backend.lib.vectors import can_index_embedding
from backend.modules.rag.application.embedding_service import EmbeddingService
from backend.modules.rag.application.retrieval_filters import exclude_injection_flagged_chunks
from backend.modules.rag.application.retrieval_ranker import HybridRetrievalRanker
from backend.modules.rag.domain.models import RetrievalOutcome, RetrievedChunk
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.pgvector_errors import PgVectorUnavailableError
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.modules.rag.infrastructure.vector_store_adapter import build_vector_store
from backend.observability.instruments import set_current_span_attributes
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _deduplicate_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Keep one bounded retrieval row per chunk ID, preferring highest score."""

    by_id: dict[str, RetrievedChunk] = {}
    order: list[str] = []
    for chunk in chunks:
        if chunk.chunk_id not in by_id:
            by_id[chunk.chunk_id] = chunk
            order.append(chunk.chunk_id)
        elif chunk.score > by_id[chunk.chunk_id].score:
            by_id[chunk.chunk_id] = chunk
    return [by_id[chunk_id] for chunk_id in order]


class RetrievalService:
    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()
        self.vector_store = build_vector_store(db, self.config)
        self.repo = RagRepository(db)
        self.embeddings = EmbeddingService(self.config)
        self.ranker = HybridRetrievalRanker()

    async def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        organization_id: str | None = None,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> RetrievalOutcome:
        if not self.config.enabled:
            return RetrievalOutcome(chunks=[])

        resolved_top_k = top_k or self.config.top_k
        effective_filters = dict(filters or {})
        requested_document_ids = effective_filters.get("document_ids")
        if requested_document_ids:
            valid_document_ids = await self.repo.filter_document_ids_for_user(
                user_id,
                list(dict.fromkeys(requested_document_ids)),
                project_id=project_id,
                organization_id=organization_id,
            )
            if not valid_document_ids:
                return RetrievalOutcome(chunks=[], no_matches=True)
            effective_filters["document_ids"] = valid_document_ids
        filters = effective_filters or None
        rerank_enabled = getattr(self.config, "rerank_enabled", False)
        cache_variant = (
            ("hybrid-v1" if rerank_enabled else "vector-v1")
            + f":{getattr(self.config, 'embedding_provider', 'unknown')}"
            + f":{getattr(self.config, 'embedding_model', 'unknown')}"
            + f":{getattr(self.config, 'embedding_dimensions', 'unknown')}"
        )
        started = perf_counter()
        try:
            cached = await get_cached_retrieval(
                user_id=user_id,
                project_id=project_id,
                query=query,
                top_k=resolved_top_k,
                filters=filters,
                variant=cache_variant,
                organization_id=organization_id,
            )
            if cached is not None:
                set_current_span_attributes(
                    module="rag",
                    cache_hit=True,
                    retrieval_candidate_count=len(cached),
                )
                cached = _deduplicate_chunks(cached)
                filtered, removed = exclude_injection_flagged_chunks(cached)
                if removed:
                    metrics.rag_injection_chunks_filtered_total.inc(removed)
                metrics.rag_retrieved_chunks.observe(len(filtered))
                logger.debug(
                    "RAG retrieval cache_hit user=%s chunks=%s injection_filtered=%s",
                    user_id,
                    len(filtered),
                    removed,
                )
                return RetrievalOutcome(
                    chunks=filtered,
                    injection_chunks_filtered=removed,
                    no_matches=len(filtered) == 0,
                )

            query_embedding = (await self.embeddings.embed_texts([query]))[0]
            if not can_index_embedding(
                query_embedding,
                expected_dimensions=self.config.embedding_dimensions,
            ):
                logger.warning(
                    "Query embedding dimension mismatch for user=%s (got %s, expected %s)",
                    user_id,
                    len(query_embedding),
                    self.config.embedding_dimensions,
                )
                metrics.rag_vector_unavailable_total.inc()
                metrics.rag_vector_readiness_failure_total.labels(
                    reason="query_dimension_mismatch"
                ).inc()
                metrics.rag_retrieval_degraded_total.inc()
                set_current_span_attributes(fallback_reason="embedding_dimension_mismatch")
                return RetrievalOutcome(
                    chunks=[],
                    degraded=True,
                    degradation_reason="embedding_dimension_mismatch",
                )

            multiplier = getattr(self.config, "rerank_candidate_multiplier", 1)
            candidate_limit = (
                min(50, resolved_top_k * multiplier) if rerank_enabled else resolved_top_k
            )
            raw_results = await self.vector_store.similarity_search(
                query,
                user_id=user_id,
                project_id=project_id,
                top_k=candidate_limit,
                filters=filters,
                query_embedding=query_embedding,
                organization_id=organization_id,
            )
            set_current_span_attributes(
                module="rag",
                cache_hit=False,
                retrieval_candidate_count=len(raw_results),
                retrieval_top_k=resolved_top_k,
            )
            raw_results = _deduplicate_chunks(raw_results)
            if not rerank_enabled:
                raw_results = raw_results[:resolved_top_k]
            filtered, removed = exclude_injection_flagged_chunks(raw_results)
            if removed:
                metrics.rag_injection_chunks_filtered_total.inc(removed)
            if rerank_enabled:
                rerank_started = perf_counter()
                filtered = self.ranker.rerank(query, filtered, limit=resolved_top_k)
                metrics.rag_rerank_latency_ms.observe((perf_counter() - rerank_started) * 1000)

            outcome = RetrievalOutcome(
                chunks=filtered,
                injection_chunks_filtered=removed,
                no_matches=len(filtered) == 0,
            )
            if outcome.no_matches and raw_results and removed == len(raw_results):
                outcome.degradation_reason = "injection_filtered_all_matches"
            if outcome.degradation_reason:
                set_current_span_attributes(fallback_reason=outcome.degradation_reason)

            if removed == 0:
                await set_cached_retrieval(
                    user_id=user_id,
                    project_id=project_id,
                    query=query,
                    top_k=resolved_top_k,
                    filters=filters,
                    chunks=filtered,
                    variant=cache_variant,
                    organization_id=organization_id,
                )
            metrics.rag_retrieved_chunks.observe(len(filtered))
            if outcome.no_matches:
                metrics.rag_retrieval_no_match_total.inc()
            duration_ms = (perf_counter() - started) * 1000
            if outcome.degraded:
                logger.warning(
                    "RAG retrieval degraded user=%s duration_ms=%.2f reason=%s chunks=%s",
                    user_id,
                    duration_ms,
                    outcome.degradation_reason,
                    len(filtered),
                )
            elif outcome.no_matches:
                logger.info(
                    "RAG retrieval no_matches user=%s duration_ms=%.2f chunks=%s",
                    user_id,
                    duration_ms,
                    len(filtered),
                )
            else:
                logger.info(
                    "RAG retrieval completed user=%s duration_ms=%.2f "
                    "chunks=%s injection_filtered=%s",
                    user_id,
                    duration_ms,
                    len(filtered),
                    removed,
                )
            if duration_ms >= settings.SLOW_EXTERNAL_CALL_MS:
                logger.warning(
                    "slow_rag_retrieval user=%s duration_ms=%.2f",
                    user_id,
                    duration_ms,
                )
            return outcome
        except PgVectorUnavailableError as exc:
            logger.warning(
                "RAG pgvector unavailable user=%s reason=%s",
                user_id,
                exc.reason,
            )
            metrics.rag_vector_unavailable_total.inc()
            metrics.rag_vector_readiness_failure_total.labels(reason=exc.reason).inc()
            metrics.rag_retrieval_degraded_total.inc()
            set_current_span_attributes(fallback_reason="pgvector_" + exc.reason)
            return RetrievalOutcome(
                chunks=[],
                degraded=True,
                degradation_reason=f"pgvector_{exc.reason}",
            )
        except Exception:
            logger.exception("RAG retrieval failed for user=%s", user_id)
            metrics.rag_vector_unavailable_total.inc()
            metrics.rag_retrieval_degraded_total.inc()
            set_current_span_attributes(fallback_reason="retrieval_failed")
            return RetrievalOutcome(
                chunks=[],
                degraded=True,
                degradation_reason="retrieval_failed",
            )
        finally:
            metrics.rag_retrieval_latency_ms.observe((perf_counter() - started) * 1000)
