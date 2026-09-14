from __future__ import annotations

import json
import logging
from time import perf_counter

from backend.core.config import settings
from backend.lib.concurrency import bounded_gather
from backend.lib.retrieval_cache import get_cached_retrieval, set_cached_retrieval
from backend.lib.vectors import can_index_embedding
from backend.modules.rag.application.candidate_expansion import (
    CandidatePlan,
    resolve_candidate_plan,
)
from backend.modules.rag.application.embedding_service import EmbeddingService
from backend.modules.rag.application.pipeline_versions import pipeline_cache_variant_suffix
from backend.modules.rag.application.quality_strategies import (
    apply_quality_strategies,
    merge_neighbor_chunks,
    quality_options_from_config,
)
from backend.modules.rag.application.rerankers import build_reranker
from backend.modules.rag.application.retrieval_filters import exclude_injection_flagged_chunks
from backend.modules.rag.application.retrieval_ranker import reciprocal_rank_fuse
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
        self.ranker = build_reranker(
            enabled=bool(getattr(self.config, "rerank_enabled", False)),
            backend=str(getattr(self.config, "reranker_backend", "lightweight")),
        )

    async def _active_index_version_id(self) -> str | None:
        from backend.modules.rag.application.index_version_service import IndexVersionService

        active = await IndexVersionService(self.db, config=self.config).get_active_version()
        return active.id if active is not None else None

    async def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        organization_id: str | None = None,
        top_k: int | None = None,
        filters: dict | None = None,
        strategy: str | None = None,
    ) -> RetrievalOutcome:
        if not self.config.enabled:
            return RetrievalOutcome(chunks=[])

        resolved_top_k = top_k or self.config.top_k
        plan = resolve_candidate_plan(
            self.config,
            top_k=resolved_top_k,
            strategy=strategy,
        )
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

        try:
            active_version_id = await self._active_index_version_id()
        except Exception:
            active_version_id = None
        if not active_version_id:
            logger.warning("RAG retrieval skipped: no active index version")
            return RetrievalOutcome(
                chunks=[],
                degraded=True,
                degradation_reason="no_active_index_version",
            )
        effective_filters["index_version_id"] = active_version_id
        filters = effective_filters or None
        cache_variant = (
            plan.cache_variant_prefix
            + f":{getattr(self.config, 'embedding_provider', 'unknown')}"
            + f":{getattr(self.config, 'embedding_model', 'unknown')}"
            + f":{getattr(self.config, 'embedding_dimensions', 'unknown')}"
            + f":reranker={getattr(self.config, 'reranker_backend', 'lightweight')}"
            + f":{pipeline_cache_variant_suffix()}"
            + f":idx={active_version_id}"
            + f":q={int(getattr(self.config, 'dedup_exact_enabled', False))}"
            f"{int(getattr(self.config, 'dedup_near_enabled', False))}"
            f"{int(getattr(self.config, 'mmr_enabled', False))}"
            f"{int(getattr(self.config, 'neighbor_expansion_enabled', False))}"
            f"{int(getattr(self.config, 'parent_child_retrieval_enabled', False))}"
            f"{int(getattr(self.config, 'per_document_limit', 0) or 0)}"
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
                    retrieval_strategy=plan.strategy,
                )
                cached = _deduplicate_chunks(cached)
                filtered, removed = exclude_injection_flagged_chunks(cached)
                if removed:
                    metrics.rag_injection_chunks_filtered_total.inc(removed)
                metrics.rag_retrieved_chunks.observe(len(filtered))
                try:
                    from backend.observability.request_diagnostics import record_rag_chunks

                    record_rag_chunks(len(filtered))
                except Exception:
                    pass
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

            query_embedding: list[float] | None = None
            if plan.needs_embedding:
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

            raw_results = await self._retrieve_candidates(
                query,
                user_id=user_id,
                project_id=project_id,
                organization_id=organization_id,
                filters=filters,
                query_embedding=query_embedding,
                plan=plan,
            )
            set_current_span_attributes(
                module="rag",
                cache_hit=False,
                retrieval_candidate_count=len(raw_results),
                retrieval_top_k=resolved_top_k,
                retrieval_strategy=plan.strategy,
            )
            raw_results = _deduplicate_chunks(raw_results)
            quality = quality_options_from_config(self.config)
            # Keep a larger pool before optional post-rerank / quality steps.
            pool_limit = max(plan.final_top_k, plan.fuse_limit)
            if not plan.post_rerank:
                raw_results = raw_results[:pool_limit]
            filtered, removed = exclude_injection_flagged_chunks(raw_results)
            if removed:
                metrics.rag_injection_chunks_filtered_total.inc(removed)
            if plan.post_rerank:
                rerank_started = perf_counter()
                filtered = self.ranker.rerank(query, filtered, limit=pool_limit)
                metrics.rag_rerank_latency_ms.observe((perf_counter() - rerank_started) * 1000)
            parents_by_doc_index: dict[tuple[str, int], str] | None = None
            if quality.parent_child_expand:
                parents_by_doc_index = await self._load_parent_texts(filtered)
            filtered = apply_quality_strategies(
                filtered,
                options=quality,
                final_limit=plan.final_top_k,
                parents_by_doc_index=parents_by_doc_index,
            )
            if quality.neighbor_expansion and quality.neighbor_window > 0:
                filtered = await self._expand_neighbors(
                    filtered,
                    user_id=user_id,
                    organization_id=organization_id,
                    window=quality.neighbor_window,
                    limit=plan.final_top_k,
                )

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
            try:
                from backend.observability.request_diagnostics import record_rag_chunks

                record_rag_chunks(len(filtered))
            except Exception:
                pass
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
                    "RAG retrieval completed user=%s strategy=%s duration_ms=%.2f "
                    "chunks=%s injection_filtered=%s",
                    user_id,
                    plan.strategy,
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

    async def _retrieve_candidates(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        organization_id: str | None,
        filters: dict | None,
        query_embedding: list[float] | None,
        plan: CandidatePlan,
    ) -> list[RetrievedChunk]:
        """Run configured lanes and fuse. Expansion limits come only from ``plan``."""

        document_ids = (filters or {}).get("document_ids")
        source_type = (filters or {}).get("source_type")
        index_version_id = (filters or {}).get("index_version_id")

        async def _vector_lane() -> list[RetrievedChunk]:
            assert query_embedding is not None
            return await self.vector_store.similarity_search(
                query,
                user_id=user_id,
                project_id=project_id,
                top_k=plan.vector_limit,
                filters=filters,
                query_embedding=query_embedding,
                organization_id=organization_id,
            )

        async def _lexical_lane() -> list[RetrievedChunk]:
            return await self.repo.lexical_search_indexed(
                user_id=user_id,
                project_id=project_id,
                document_ids=document_ids,
                source_type=source_type,
                query=query,
                candidate_limit=plan.lexical_limit,
                organization_id=organization_id,
                index_version_id=index_version_id,
            )

        if plan.strategy == "vector":
            return await _vector_lane()

        if plan.strategy == "lexical":
            return await _lexical_lane()

        vector_task = _vector_lane()
        lexical_task = _lexical_lane()
        vector_chunks, lexical_chunks = await bounded_gather(
            [vector_task, lexical_task],
            limit=2,
            return_exceptions=True,
            kind="rag_hybrid_retrieve",
        )
        if isinstance(vector_chunks, BaseException):
            raise vector_chunks
        if isinstance(lexical_chunks, BaseException):
            logger.warning(
                "Lexical retrieval lane failed; falling back to vector-only candidates",
                exc_info=lexical_chunks,
            )
            lexical_chunks = []
        if not lexical_chunks:
            return list(vector_chunks)[: plan.fuse_limit]
        return reciprocal_rank_fuse(
            [list(vector_chunks), list(lexical_chunks)],
            limit=plan.fuse_limit,
            k=plan.rrf_k,
        )

    async def _load_parent_texts(
        self, chunks: list[RetrievedChunk]
    ) -> dict[tuple[str, int], str]:
        """Resolve parent chunk bodies by (document_id, parent_chunk_index)."""

        wanted: set[tuple[str, int]] = set()
        for chunk in chunks:
            if chunk.metadata.get("parent_content"):
                continue
            parent_idx = chunk.metadata.get("parent_chunk_index")
            if isinstance(parent_idx, int):
                wanted.add((chunk.document_id, parent_idx))
        if not wanted:
            return {}

        parents: dict[tuple[str, int], str] = {}
        for document_id in {doc_id for doc_id, _ in wanted}:
            rows, _ = await self.repo.list_chunks_for_document(
                document_id, limit=5000, offset=0
            )
            for row in rows:
                key = (row.document_id, row.chunk_index)
                if key not in wanted:
                    continue
                meta = json.loads(row.metadata_json or "{}")
                if meta.get("chunk_role") == "child":
                    continue
                parents[key] = row.content
        return parents

    async def _expand_neighbors(
        self,
        chunks: list[RetrievedChunk],
        *,
        user_id: str,
        organization_id: str | None,
        window: int,
        limit: int,
    ) -> list[RetrievedChunk]:
        if not chunks or window < 1:
            return chunks[:limit]

        wanted: set[tuple[str, int]] = set()
        for chunk in chunks:
            for offset in range(1, window + 1):
                wanted.add((chunk.document_id, chunk.chunk_index - offset))
                wanted.add((chunk.document_id, chunk.chunk_index + offset))
        neighbors: list[RetrievedChunk] = []
        for document_id in {chunk.document_id for chunk in chunks}:
            rows, _ = await self.repo.list_chunks_for_document(
                document_id, limit=5000, offset=0
            )
            for row in rows:
                if row.user_id != user_id and (
                    organization_id is None or row.organization_id != organization_id
                ):
                    continue
                if (row.document_id, row.chunk_index) not in wanted:
                    continue
                meta = json.loads(row.metadata_json or "{}")
                neighbors.append(
                    RetrievedChunk(
                        chunk_id=row.id,
                        document_id=row.document_id,
                        content=row.content,
                        score=0.0,
                        filename=str(meta.get("filename") or ""),
                        chunk_index=row.chunk_index,
                        page_number=meta.get("page_number"),
                        metadata=meta,
                    )
                )
        return merge_neighbor_chunks(chunks, neighbors, limit=limit)
