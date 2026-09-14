"""Phase 12 quality strategy and reranker unit tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.modules.rag.application.chunking_service import ChunkingService
from backend.modules.rag.application.embedding_service import EmbeddingService
from backend.modules.rag.application.quality_strategies import (
    QualityOptions,
    apply_quality_strategies,
    exact_deduplicate,
    expand_parent_content,
    mmr_select,
    near_deduplicate,
)
from backend.modules.rag.application.rerankers import build_reranker
from backend.modules.rag.domain.models import ParsedDocument, RetrievedChunk


def _chunk(**overrides) -> RetrievedChunk:
    base = {
        "chunk_id": "c1",
        "document_id": "doc-1",
        "content": "alpha beta gamma",
        "score": 0.9,
        "filename": "a.txt",
        "chunk_index": 0,
    }
    base.update(overrides)
    return RetrievedChunk(**base)


class QualityStrategyTest(unittest.TestCase):
    def test_exact_dedup_removes_duplicate_content(self) -> None:
        chunks = [
            _chunk(chunk_id="a", content="same text", score=0.9),
            _chunk(chunk_id="b", content="same text", score=0.8),
            _chunk(chunk_id="c", content="other", score=0.7),
        ]
        kept = exact_deduplicate(chunks)
        self.assertEqual([item.chunk_id for item in kept], ["a", "c"])

    def test_near_dedup_removes_high_overlap(self) -> None:
        chunks = [
            _chunk(chunk_id="a", content="rotate database credentials every ninety days"),
            _chunk(chunk_id="b", content="rotate database credentials every ninety days now"),
            _chunk(chunk_id="c", content="office snack policy"),
        ]
        kept = near_deduplicate(chunks, threshold=0.7)
        self.assertEqual(kept[0].chunk_id, "a")
        self.assertEqual(kept[-1].chunk_id, "c")
        self.assertEqual(len(kept), 2)

    def test_mmr_prefers_diverse_second_hit(self) -> None:
        chunks = [
            _chunk(chunk_id="a", content="postgres backup policy", score=1.0),
            _chunk(chunk_id="b", content="postgres backup schedule", score=0.95),
            _chunk(chunk_id="c", content="redis cache fail open", score=0.9),
        ]
        selected = mmr_select(chunks, limit=2, lambda_mult=0.5)
        self.assertEqual(selected[0].chunk_id, "a")
        self.assertEqual(selected[1].chunk_id, "c")

    def test_parent_child_expand_swaps_content(self) -> None:
        chunks = [
            _chunk(
                chunk_id="child",
                content="child slice",
                metadata={"parent_chunk_index": 0},
            )
        ]
        expanded = expand_parent_content(
            chunks,
            parents_by_doc_index={("doc-1", 0): "full parent section text"},
        )
        self.assertEqual(expanded[0].content, "full parent section text")
        self.assertTrue(expanded[0].metadata["retrieved_as_child"])
        self.assertNotIn("parent_content", expanded[0].metadata)

    def test_disabled_options_preserve_order(self) -> None:
        chunks = [_chunk(chunk_id="a"), _chunk(chunk_id="b")]
        result = apply_quality_strategies(
            chunks, options=QualityOptions(), final_limit=2
        )
        self.assertEqual([item.chunk_id for item in result], ["a", "b"])


class RerankerFactoryTest(unittest.TestCase):
    def test_disabled_uses_noop(self) -> None:
        ranker = build_reranker(enabled=False, backend="lightweight")
        self.assertEqual(ranker.name, "none")

    def test_lightweight_backend(self) -> None:
        ranker = build_reranker(enabled=True, backend="lightweight")
        self.assertEqual(ranker.name, "lightweight")

    def test_expensive_backend_falls_back_without_raising(self) -> None:
        ranker = build_reranker(enabled=True, backend="cross_encoder")
        chunks = [_chunk(), _chunk(chunk_id="c2")]
        ranked = ranker.rerank("query", chunks, limit=1)
        self.assertEqual(len(ranked), 1)


class DocumentAwareChunkingTest(unittest.IsolatedAsyncioTestCase):
    async def test_stores_prev_next_and_section_path(self) -> None:
        service = ChunkingService(
            SimpleNamespace(
                chunk_size=40,
                chunk_overlap=5,
                embedding_model=None,
                document_aware_chunking=True,
                parent_child_chunking=False,
            )
        )
        docs = [
            ParsedDocument(
                content=("## Intro\n\n" + ("word " * 40) + "\n\n## Details\n\n" + ("item " * 40)),
                metadata={"format": "markdown", "section_heading": "Intro"},
            )
        ]
        chunks = await service.chunk(
            docs,
            document_id="doc-1",
            user_id="user-1",
            filename="notes.md",
        )
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].metadata["prev_chunk_index"], None)
        self.assertEqual(chunks[0].metadata["next_chunk_index"], 1)
        self.assertIn("section_path", chunks[0].metadata)
        self.assertEqual(chunks[0].metadata["chunk_token_count"], chunks[0].token_count)

    async def test_parent_child_emits_child_refs_without_parent_text(self) -> None:
        service = ChunkingService(
            SimpleNamespace(
                chunk_size=80,
                chunk_overlap=10,
                embedding_model=None,
                document_aware_chunking=False,
                parent_child_chunking=True,
                parent_child_child_size=8,
                parent_child_child_overlap=2,
            )
        )
        docs = [ParsedDocument(content=("token " * 40).strip(), metadata={"format": "txt"})]
        chunks = await service.chunk(
            docs,
            document_id="doc-1",
            user_id="user-1",
            filename="notes.txt",
        )
        parents = [c for c in chunks if c.metadata.get("chunk_role") == "parent"]
        children = [c for c in chunks if c.metadata.get("chunk_role") == "child"]
        self.assertGreaterEqual(len(parents), 1)
        self.assertGreaterEqual(len(children), 2)
        self.assertTrue(all(not child.metadata.get("parent_content") for child in children))
        self.assertTrue(
            all(isinstance(child.metadata.get("parent_chunk_index"), int) for child in children)
        )
        self.assertTrue(all("token_start" in child.metadata for child in children))
        self.assertTrue(all("char_start" in child.metadata for child in children))

    async def test_parent_child_handles_multilingual_and_code_like_text(self) -> None:
        service = ChunkingService(
            SimpleNamespace(
                chunk_size=40,
                chunk_overlap=5,
                embedding_model=None,
                document_aware_chunking=True,
                parent_child_chunking=True,
                parent_child_child_size=12,
                parent_child_child_overlap=2,
            )
        )
        docs = [
            ParsedDocument(
                content=(
                    "## Başlık\n"
                    "Türkçe metin ve İngilizce mixed content.\n"
                    "```python\n"
                    "def rotate(url='https://example.com/very/long/path?x=1&y=2'):\n"
                    "    return url\n"
                    "```\n"
                    "- item one\n"
                    "- item two\n"
                ),
                metadata={"format": "md", "section_heading": "Başlık"},
            )
        ]
        chunks = await service.chunk(
            docs,
            document_id="doc-tr",
            user_id="user-1",
            filename="notes.md",
        )
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(any(c.metadata.get("chunk_role") == "child" for c in chunks))


class EmbeddingBatchingTest(unittest.IsolatedAsyncioTestCase):
    async def test_batches_with_bounded_concurrency(self) -> None:
        service = EmbeddingService(
            SimpleNamespace(
                embedding_provider="local",
                embedding_model="hash",
                embedding_dimensions=4,
                embedding_batch_size=2,
                embedding_concurrency=2,
                embedding_max_retries=0,
                embedding_allow_partial_failure=False,
            )
        )
        calls: list[list[str]] = []

        async def _fake(batch: list[str]) -> list[list[float]]:
            calls.append(list(batch))
            return [[0.1] * 4 for _ in batch]

        service._adapter.embed_texts = AsyncMock(side_effect=_fake)

        async def _passthrough(**kwargs):
            return await kwargs["embed_fn"](kwargs["texts"])

        with patch(
            "backend.modules.rag.application.embedding_service.embed_texts_with_cache",
            new=AsyncMock(side_effect=_passthrough),
        ):
            vectors = await service.embed_texts(["a", "b", "c", "d"])
        self.assertEqual(len(vectors), 4)
        self.assertEqual(len(calls), 2)

    async def test_rejects_zero_vectors_and_never_fills_zeros_on_partial(self) -> None:
        service = EmbeddingService(
            SimpleNamespace(
                embedding_provider="local",
                embedding_model="hash",
                embedding_dimensions=4,
                embedding_batch_size=2,
                embedding_concurrency=2,
                embedding_max_retries=0,
                embedding_allow_partial_failure=True,
            )
        )

        async def _fail_second(batch: list[str]) -> list[list[float]]:
            if batch == ["c", "d"]:
                raise RuntimeError("provider down")
            return [[0.0] * 4 for _ in batch]

        service._adapter.embed_texts = AsyncMock(side_effect=_fail_second)

        async def _passthrough(**kwargs):
            return await kwargs["embed_fn"](kwargs["texts"])

        with patch(
            "backend.modules.rag.application.embedding_service.embed_texts_with_cache",
            new=AsyncMock(side_effect=_passthrough),
        ), self.assertRaises((RuntimeError, ValueError)):
            await service.embed_texts(["a", "b", "c", "d"])


class EmbeddingValidationHelpersTest(unittest.TestCase):
    def test_can_index_rejects_nan_inf_and_zero(self) -> None:
        from backend.lib.vectors import can_index_embedding

        self.assertFalse(can_index_embedding([0.0, 0.0], expected_dimensions=2))
        self.assertFalse(can_index_embedding([float("nan"), 1.0], expected_dimensions=2))
        self.assertFalse(can_index_embedding([float("inf"), 1.0], expected_dimensions=2))
        self.assertTrue(can_index_embedding([0.1, -0.2], expected_dimensions=2))
