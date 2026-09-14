"""Single candidate-expansion layer for RAG retrieval.

All lane limit / RRF sizing decisions happen here. Callers must not multiply
``top_k`` again before vector or lexical search.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RETRIEVAL_STRATEGIES = frozenset({"vector", "lexical", "hybrid_rrf"})
_MAX_CANDIDATES = 50
_DEFAULT_RRF_K = 60


@dataclass(frozen=True, slots=True)
class CandidatePlan:
    """Resolved lane limits and fusion settings for one retrieve call."""

    strategy: str
    vector_limit: int
    lexical_limit: int
    fuse_limit: int
    final_top_k: int
    rrf_k: int
    post_rerank: bool
    needs_embedding: bool

    @property
    def cache_variant_prefix(self) -> str:
        return (
            f"{self.strategy}"
            f":v{self.vector_limit}"
            f":l{self.lexical_limit}"
            f":rrf{self.rrf_k}"
            f":rerank{int(self.post_rerank)}"
        )


def normalize_retrieval_strategy(value: str | None) -> str:
    strategy = (value or "hybrid_rrf").strip().lower()
    if strategy not in RETRIEVAL_STRATEGIES:
        raise ValueError(
            f"Unknown retrieval strategy {value!r}; "
            f"expected one of {sorted(RETRIEVAL_STRATEGIES)}"
        )
    return strategy


def resolve_candidate_plan(
    config: Any,
    *,
    top_k: int,
    strategy: str | None = None,
) -> CandidatePlan:
    """Resolve expansion once from config + request top_k.

    Explicit ``vector_candidate_count`` / ``lexical_candidate_count`` win.
    Otherwise a single ``rerank_candidate_multiplier`` expands the pool when
    hybrid fusion or post-fusion rerank needs more than ``top_k`` rows.
    """

    resolved_strategy = normalize_retrieval_strategy(
        strategy if strategy is not None else getattr(config, "retrieval_strategy", None)
    )
    multiplier = max(1, int(getattr(config, "rerank_candidate_multiplier", 1) or 1))
    post_rerank = bool(getattr(config, "rerank_enabled", False))
    needs_expansion = resolved_strategy == "hybrid_rrf" or post_rerank
    derived = min(_MAX_CANDIDATES, top_k * multiplier) if needs_expansion else top_k

    def _lane_limit(explicit: int | None) -> int:
        if explicit is not None and int(explicit) > 0:
            return min(_MAX_CANDIDATES, int(explicit))
        return derived

    explicit_vector = getattr(config, "vector_candidate_count", 0) or 0
    explicit_lexical = getattr(config, "lexical_candidate_count", 0) or 0
    vector_limit = (
        _lane_limit(explicit_vector) if resolved_strategy in {"vector", "hybrid_rrf"} else 0
    )
    lexical_limit = (
        _lane_limit(explicit_lexical) if resolved_strategy in {"lexical", "hybrid_rrf"} else 0
    )
    fuse_limit = max(vector_limit, lexical_limit, top_k)
    rrf_k = max(1, int(getattr(config, "rrf_k", _DEFAULT_RRF_K) or _DEFAULT_RRF_K))
    return CandidatePlan(
        strategy=resolved_strategy,
        vector_limit=vector_limit,
        lexical_limit=lexical_limit,
        fuse_limit=fuse_limit,
        final_top_k=top_k,
        rrf_k=rrf_k,
        post_rerank=post_rerank and resolved_strategy != "lexical",
        needs_embedding=resolved_strategy in {"vector", "hybrid_rrf"},
    )
