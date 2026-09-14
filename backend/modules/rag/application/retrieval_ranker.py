from __future__ import annotations

import re
from collections import Counter

from backend.modules.rag.domain.models import RetrievedChunk

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")


class HybridRetrievalRanker:
    """Fuse pgvector candidates with PostgreSQL lexical evidence.

    The repository supplies ``lexical_score`` from ``ts_rank_cd`` when the
    indexed path is available. The local token overlap remains a bounded,
    dependency-free fallback for tests and older cached candidates.
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
