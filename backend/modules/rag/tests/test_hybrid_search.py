"""Exact-match and semantic hybrid retrieval strategy tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.modules.rag.application.candidate_expansion import resolve_candidate_plan
from backend.modules.rag.application.retrieval_ranker import reciprocal_rank_fuse
from backend.modules.rag.application.retrieval_service import RetrievalService
from backend.modules.rag.domain.models import RetrievedChunk


def _chunk(**overrides) -> RetrievedChunk:
    base = {
        "chunk_id": "c1",
        "document_id": "doc-1",
        "content": "safe content",
        "score": 0.9,
        "filename": "notes.txt",
        "chunk_index": 0,
    }
    base.update(overrides)
    return RetrievedChunk(**base)


class CandidateExpansionTest(unittest.TestCase):
    def test_multiplier_applied_once_for_hybrid(self) -> None:
        plan = resolve_candidate_plan(
            SimpleNamespace(
                retrieval_strategy="hybrid_rrf",
                vector_candidate_count=0,
                lexical_candidate_count=0,
                rrf_k=60,
                rerank_enabled=True,
                rerank_candidate_multiplier=3,
            ),
            top_k=5,
        )
        self.assertEqual(plan.vector_limit, 15)
        self.assertEqual(plan.lexical_limit, 15)
        self.assertEqual(plan.fuse_limit, 15)
        self.assertEqual(plan.final_top_k, 5)

    def test_explicit_lane_counts_skip_multiplier(self) -> None:
        plan = resolve_candidate_plan(
            SimpleNamespace(
                retrieval_strategy="hybrid_rrf",
                vector_candidate_count=8,
                lexical_candidate_count=12,
                rrf_k=40,
                rerank_enabled=True,
                rerank_candidate_multiplier=3,
            ),
            top_k=5,
        )
        self.assertEqual(plan.vector_limit, 8)
        self.assertEqual(plan.lexical_limit, 12)
        self.assertEqual(plan.fuse_limit, 12)
        self.assertEqual(plan.rrf_k, 40)

    def test_lexical_strategy_skips_embedding(self) -> None:
        plan = resolve_candidate_plan(
            SimpleNamespace(
                retrieval_strategy="lexical",
                vector_candidate_count=0,
                lexical_candidate_count=0,
                rrf_k=60,
                rerank_enabled=True,
                rerank_candidate_multiplier=3,
            ),
            top_k=5,
        )
        self.assertFalse(plan.needs_embedding)
        self.assertEqual(plan.vector_limit, 0)
        self.assertEqual(plan.lexical_limit, 15)
        self.assertFalse(plan.post_rerank)


class ExactMatchHybridTest(unittest.TestCase):
    def test_rrf_recovers_exact_tokens_missed_by_vector(self) -> None:
        cases = (
            ("ticket id TCK-94821", "Ticket TCK-94821 is assigned to on-call."),
            ("acronym SOC2", "Our SOC2 control catalog lives in the trust center."),
            ("error ZX-204", "Error code ZX-204 means an invitation link has expired."),
            ("model NX-9000", "Product model NX-9000 ships with dual power supplies."),
            ("invoice 4815162342", "Invoice 4815162342 was paid on Tuesday."),
            ("Dr. Aisha Rahman", "Contact Dr. Aisha Rahman for pharmacy escalations."),
        )
        for query_hint, exact_content in cases:
            with self.subTest(query=query_hint):
                vector_lane = [
                    _chunk(chunk_id="semantic-a", score=0.97, content="unrelated policy prose"),
                    _chunk(chunk_id="semantic-b", score=0.95, content="another unrelated paragraph"),
                ]
                lexical_lane = [
                    _chunk(chunk_id="exact", score=0.99, content=exact_content),
                ]
                fused = reciprocal_rank_fuse([vector_lane, lexical_lane], limit=3, k=60)
                self.assertIn("exact", {chunk.chunk_id for chunk in fused})
                self.assertEqual(fused[0].chunk_id, "exact")


class SemanticHybridTest(unittest.TestCase):
    def test_rrf_keeps_strong_semantic_hit_without_exact_tokens(self) -> None:
        vector_lane = [
            _chunk(
                chunk_id="semantic",
                score=0.96,
                content="Rotate database credentials every ninety days for production.",
            ),
            _chunk(chunk_id="noise", score=0.4, content="office snack policy"),
        ]
        # Paraphrase overlap is weak but present; fusion should still prefer the
        # strong ANN hit over an unrelated lexical-only snack policy chunk.
        lexical_lane = [
            _chunk(
                chunk_id="semantic",
                score=0.2,
                content="Rotate database credentials every ninety days for production.",
            ),
            _chunk(chunk_id="noise", score=0.15, content="office snack policy"),
        ]
        fused = reciprocal_rank_fuse([vector_lane, lexical_lane], limit=2, k=60)
        self.assertEqual(fused[0].chunk_id, "semantic")


class RetrievalStrategyServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_lexical_strategy_skips_embeddings_and_vector_store(self) -> None:
        db = MagicMock()
        service = RetrievalService(db)
        service.config = SimpleNamespace(
            enabled=True,
            top_k=3,
            embedding_dimensions=2,
            retrieval_strategy="lexical",
            vector_candidate_count=0,
            lexical_candidate_count=0,
            rrf_k=60,
            rerank_enabled=True,
            rerank_candidate_multiplier=3,
            embedding_provider="local",
            embedding_model="hash",
        )
        service.embeddings = MagicMock()
        service.embeddings.embed_texts = AsyncMock(return_value=[[1.0, 0.0]])
        service.vector_store = MagicMock()
        service.vector_store.similarity_search = AsyncMock(return_value=[])
        service.repo.lexical_search_indexed = AsyncMock(
            return_value=[_chunk(chunk_id="lex-1", content="Error ZX-204 expired")]
        )

        with (
            patch(
                "backend.modules.rag.application.retrieval_service.get_cached_retrieval",
                AsyncMock(return_value=None),
            ),
            patch(
                "backend.modules.rag.application.retrieval_service.set_cached_retrieval",
                AsyncMock(),
            ),
        ):
            outcome = await service.retrieve(
                "ZX-204",
                user_id="user-1",
                project_id=None,
                strategy="lexical",
            )

        service.embeddings.embed_texts.assert_not_awaited()
        service.vector_store.similarity_search.assert_not_awaited()
        service.repo.lexical_search_indexed.assert_awaited_once()
        self.assertEqual(outcome.chunks[0].chunk_id, "lex-1")

    async def test_vector_strategy_skips_lexical_lane(self) -> None:
        db = MagicMock()
        service = RetrievalService(db)
        service.config = SimpleNamespace(
            enabled=True,
            top_k=2,
            embedding_dimensions=2,
            retrieval_strategy="vector",
            vector_candidate_count=0,
            lexical_candidate_count=0,
            rrf_k=60,
            rerank_enabled=False,
            rerank_candidate_multiplier=3,
            embedding_provider="local",
            embedding_model="hash",
        )
        service.embeddings = MagicMock()
        service.embeddings.embed_texts = AsyncMock(return_value=[[1.0, 0.0]])
        service.vector_store = MagicMock()
        service.vector_store.similarity_search = AsyncMock(
            return_value=[_chunk(chunk_id="vec-1")]
        )
        service.repo.lexical_search_indexed = AsyncMock(return_value=[])

        with (
            patch(
                "backend.modules.rag.application.retrieval_service.get_cached_retrieval",
                AsyncMock(return_value=None),
            ),
            patch(
                "backend.modules.rag.application.retrieval_service.set_cached_retrieval",
                AsyncMock(),
            ),
        ):
            outcome = await service.retrieve(
                "rotate credentials",
                user_id="user-1",
                project_id=None,
                strategy="vector",
            )

        service.repo.lexical_search_indexed.assert_not_awaited()
        self.assertEqual(outcome.chunks[0].chunk_id, "vec-1")
