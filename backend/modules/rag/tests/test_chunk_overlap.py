"""Chunk overlap metadata correctness and performance regressions."""

from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.modules.rag.application.chunking_service import (
    ChunkingService,
    prefix_suffix_overlap,
)
from backend.modules.rag.domain.models import ParsedDocument


def _legacy_backwards_overlap(previous: str, current: str) -> int:
    if not previous or not current:
        return 0
    max_overlap = min(len(previous), len(current))
    for size in range(max_overlap, 0, -1):
        if previous[-size:] == current[:size]:
            return size
    return 0


class PrefixSuffixOverlapTest(unittest.TestCase):
    def test_matches_legacy_backwards_scan_for_representative_pairs(self):
        cases = (
            ("", "abc"),
            ("abc", ""),
            ("hello world", "world peace"),
            ("aaaa", "aaa"),
            ("abcdef", "xyz"),
            ("overlap-me-please", "me-please-now"),
            ("A" * 200, ("A" * 50) + ("B" * 150)),
            ("short", "short" + ("x" * 1000)),
        )
        for previous, current in cases:
            with self.subTest(previous=previous[:20], current=current[:20]):
                self.assertEqual(
                    prefix_suffix_overlap(previous, current),
                    _legacy_backwards_overlap(previous, current),
                )

    def test_linear_overlap_stays_faster_than_nested_scan_on_large_chunks(self):
        previous = ("prefix-" * 800) + ("overlap" * 400)
        current = ("overlap" * 400) + ("suffix-" * 800)
        expected = _legacy_backwards_overlap(previous, current)

        started = time.perf_counter()
        nested = _legacy_backwards_overlap(previous, current)
        nested_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        linear = prefix_suffix_overlap(previous, current)
        linear_ms = (time.perf_counter() - started) * 1000

        self.assertEqual(linear, expected)
        self.assertEqual(nested, expected)
        self.assertLess(linear_ms, nested_ms)


class ChunkOverlapMetadataTest(unittest.IsolatedAsyncioTestCase):
    async def test_chunk_metadata_records_linear_overlap_between_adjacent_pieces(self):
        config = SimpleNamespace(chunk_size=40, chunk_overlap=12, embedding_model=None)
        chunker = ChunkingService(config)
        docs = [ParsedDocument(content=("word " * 80).strip(), metadata={"format": "txt"})]

        with patch(
            "backend.modules.rag.application.chunking_service.asyncio.to_thread",
            side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
        ):
            chunks = await chunker.chunk(
                docs,
                document_id="doc-1",
                user_id="user-a",
                filename="notes.txt",
            )

        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["overlap_char_count"], 0)
        for index in range(1, len(chunks)):
            expected = prefix_suffix_overlap(chunks[index - 1].content, chunks[index].content)
            self.assertEqual(chunks[index].metadata["overlap_char_count"], expected)
            if expected:
                self.assertTrue(
                    chunks[index - 1].content.endswith(chunks[index].content[:expected])
                )

    async def test_many_small_chunks_and_high_overlap_remain_correct(self):
        config = SimpleNamespace(chunk_size=20, chunk_overlap=15, embedding_model=None)
        chunker = ChunkingService(config)
        docs = [ParsedDocument(content=("abcdefghi " * 200), metadata={})]

        with patch(
            "backend.modules.rag.application.chunking_service.asyncio.to_thread",
            side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
        ):
            chunks = await chunker.chunk(
                docs,
                document_id="doc-2",
                user_id="user-a",
                filename="big.txt",
            )

        self.assertGreater(len(chunks), 5)
        for index in range(1, len(chunks)):
            self.assertEqual(
                chunks[index].metadata["overlap_char_count"],
                _legacy_backwards_overlap(chunks[index - 1].content, chunks[index].content),
            )


class ChunkingSourceContractTest(unittest.TestCase):
    def test_chunking_service_no_longer_uses_backwards_nested_scan(self):
        from pathlib import Path

        source = (
            Path(__file__).parents[1] / "application" / "chunking_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("prefix_suffix_overlap", source)
        self.assertNotIn("for size in range(max_overlap, 0, -1)", source)
        self.assertNotIn("previous_content[-size:]", source)
