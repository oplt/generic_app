"""Pluggable reranker architecture for RAG retrieval.

Expensive backends (cross-encoder / provider / LLM) are registered but not
enabled by default. Production default remains the lightweight local ranker
when ``RAG_RERANK_ENABLED=true``.
"""

from __future__ import annotations

import logging
from typing import Protocol

from backend.modules.rag.application.retrieval_ranker import HybridRetrievalRanker
from backend.modules.rag.domain.models import RetrievedChunk

logger = logging.getLogger(__name__)

RERANKER_BACKENDS = frozenset(
    {"none", "lightweight", "cross_encoder", "provider", "llm"}
)


class Reranker(Protocol):
    name: str

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        limit: int,
    ) -> list[RetrievedChunk]: ...


class NoOpReranker:
    name = "none"

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        limit: int,
    ) -> list[RetrievedChunk]:
        _ = query
        return chunks[:limit]


class LightweightLexicalReranker:
    """Existing HybridRetrievalRanker behind the pluggable interface."""

    name = "lightweight"

    def __init__(self) -> None:
        self._inner = HybridRetrievalRanker()

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        limit: int,
    ) -> list[RetrievedChunk]:
        return self._inner.rerank(query, chunks, limit=limit)


class UnavailableReranker:
    """Placeholder for optional expensive backends (not default)."""

    def __init__(self, name: str):
        self.name = name

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        limit: int,
    ) -> list[RetrievedChunk]:
        _ = query
        logger.warning(
            "Reranker backend %s is not configured; falling back to input order",
            self.name,
        )
        return chunks[:limit]


def normalize_reranker_backend(value: str | None) -> str:
    backend = (value or "lightweight").strip().lower()
    if backend not in RERANKER_BACKENDS:
        raise ValueError(
            f"Unknown reranker backend {value!r}; expected one of {sorted(RERANKER_BACKENDS)}"
        )
    return backend


def build_reranker(*, enabled: bool, backend: str) -> Reranker:
    if not enabled:
        return NoOpReranker()
    resolved = normalize_reranker_backend(backend)
    if resolved == "none":
        return NoOpReranker()
    if resolved == "lightweight":
        return LightweightLexicalReranker()
    return UnavailableReranker(resolved)
