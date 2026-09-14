from __future__ import annotations

import re
from collections import Counter

from backend.modules.rag.domain.models import RetrievedChunk

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")
_RRF_K = 60


def reciprocal_rank_fuse(
    lanes: list[list[RetrievedChunk]],
    *,
    limit: int,
    k: int = _RRF_K,
) -> list[RetrievedChunk]:
    """Merge independently generated candidate lanes with reciprocal rank fusion."""

    if limit < 1:
        return []
    fused_scores: Counter[str] = Counter()
    by_id: dict[str, RetrievedChunk] = {}
    for lane in lanes:
        for rank, chunk in enumerate(lane, start=1):
            fused_scores[chunk.chunk_id] += 1.0 / (k + rank)
            existing = by_id.get(chunk.chunk_id)
            if existing is None or chunk.score > existing.score:
                by_id[chunk.chunk_id] = chunk
    ordered_ids = sorted(
        fused_scores,
        key=lambda chunk_id: (-fused_scores[chunk_id], chunk_id),
    )
    fused: list[RetrievedChunk] = []
    for chunk_id in ordered_ids[:limit]:
        chunk = by_id[chunk_id]
        metadata = dict(chunk.metadata)
        metadata["rrf_score"] = round(fused_scores[chunk_id], 6)
        fused.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=chunk.score,
                filename=chunk.filename,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                metadata=metadata,
            )
        )
    return fused


class HybridRetrievalRanker:
    """Rerank a fused candidate set with lexical evidence.

    Prefer generating candidates from independent vector and lexical lanes, then
    call :func:`reciprocal_rank_fuse` before this reranker. Local token overlap
    remains a bounded fallback for tests and older cached candidates.
    """

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        limit: int,
    ) -> list[RetrievedChunk]:
        terms = set(_TOKEN_PATTERN.findall(query.lower()))
        if not terms or len(chunks) < 2:
            return chunks[:limit]

        query_phrase = " ".join(_TOKEN_PATTERN.findall(query.lower()))

        def score(chunk: RetrievedChunk) -> tuple[float, float]:
            content_tokens = _TOKEN_PATTERN.findall(chunk.content.lower())
            content_terms = Counter(content_tokens)
            sql_lexical = float(chunk.metadata.get("lexical_score", 0.0) or 0.0)
            lexical = max(
                len(terms & set(content_terms)) / len(terms),
                min(sql_lexical, 1.0),
            )
            term_density = sum(min(content_terms[term], 3) for term in terms) / max(
                len(content_tokens), 1
            )
            phrase_bonus = 1.0 if query_phrase and query_phrase in chunk.content.lower() else 0.0
            fused = (
                (chunk.score * 0.65)
                + (lexical * 0.2)
                + (min(term_density * 4, 1.0) * 0.1)
                + (phrase_bonus * 0.05)
            )
            return fused, chunk.score

        return sorted(chunks, key=score, reverse=True)[:limit]
