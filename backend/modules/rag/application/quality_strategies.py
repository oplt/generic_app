"""Configurable post-retrieval quality strategies (defaults preserve current behavior)."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from backend.modules.rag.domain.models import RetrievedChunk

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")


@dataclass(frozen=True, slots=True)
class QualityOptions:
    exact_dedup: bool = False
    near_dedup: bool = False
    near_dedup_threshold: float = 0.9
    per_document_limit: int = 0
    mmr_enabled: bool = False
    mmr_lambda: float = 0.7
    neighbor_expansion: bool = False
    neighbor_window: int = 1
    parent_child_expand: bool = False


def quality_options_from_config(config: Any) -> QualityOptions:
    return QualityOptions(
        exact_dedup=bool(getattr(config, "dedup_exact_enabled", False)),
        near_dedup=bool(getattr(config, "dedup_near_enabled", False)),
        near_dedup_threshold=float(getattr(config, "dedup_near_threshold", 0.9) or 0.9),
        per_document_limit=int(getattr(config, "per_document_limit", 0) or 0),
        mmr_enabled=bool(getattr(config, "mmr_enabled", False)),
        mmr_lambda=float(getattr(config, "mmr_lambda", 0.7) or 0.7),
        neighbor_expansion=bool(getattr(config, "neighbor_expansion_enabled", False)),
        neighbor_window=max(0, int(getattr(config, "neighbor_window", 1) or 0)),
        parent_child_expand=bool(getattr(config, "parent_child_retrieval_enabled", False)),
    )


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def _content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def exact_deduplicate(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    kept: list[RetrievedChunk] = []
    for chunk in chunks:
        key = _content_fingerprint(chunk.content)
        if key in seen:
            continue
        seen.add(key)
        kept.append(chunk)
    return kept


def near_deduplicate(
    chunks: list[RetrievedChunk], *, threshold: float
) -> list[RetrievedChunk]:
    kept: list[RetrievedChunk] = []
    kept_tokens: list[set[str]] = []
    for chunk in chunks:
        tokens = _tokens(chunk.content)
        if any(jaccard(tokens, prior) >= threshold for prior in kept_tokens):
            continue
        kept.append(chunk)
        kept_tokens.append(tokens)
    return kept


def apply_per_document_limit(
    chunks: list[RetrievedChunk], *, limit: int
) -> list[RetrievedChunk]:
    if limit < 1:
        return chunks
    counts: dict[str, int] = defaultdict(int)
    kept: list[RetrievedChunk] = []
    for chunk in chunks:
        if counts[chunk.document_id] >= limit:
            continue
        counts[chunk.document_id] += 1
        kept.append(chunk)
    return kept


def mmr_select(
    chunks: list[RetrievedChunk],
    *,
    limit: int,
    lambda_mult: float,
) -> list[RetrievedChunk]:
    """Maximal Marginal Relevance over token sets (no embedding required)."""

    if limit < 1 or len(chunks) <= 1:
        return chunks[:limit]
    selected: list[RetrievedChunk] = []
    selected_tokens: list[set[str]] = []
    remaining = list(chunks)
    max_score = max((chunk.score for chunk in remaining), default=1.0) or 1.0
    while remaining and len(selected) < limit:
        best_index = 0
        best_value = float("-inf")
        for index, chunk in enumerate(remaining):
            relevance = chunk.score / max_score
            redundancy = 0.0
            tokens = _tokens(chunk.content)
            if selected_tokens:
                redundancy = max(jaccard(tokens, prior) for prior in selected_tokens)
            value = lambda_mult * relevance - (1.0 - lambda_mult) * redundancy
            if value > best_value or (
                math.isclose(value, best_value) and chunk.chunk_id < remaining[best_index].chunk_id
            ):
                best_value = value
                best_index = index
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_tokens.append(_tokens(chosen.content))
    return selected


def expand_parent_content(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Replace child hit content with stored parent text when available."""

    expanded: list[RetrievedChunk] = []
    for chunk in chunks:
        parent = chunk.metadata.get("parent_content")
        if not isinstance(parent, str) or not parent.strip():
            expanded.append(chunk)
            continue
        metadata = dict(chunk.metadata)
        metadata["retrieved_as_child"] = True
        metadata["child_content"] = chunk.content
        expanded.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                content=parent,
                score=chunk.score,
                filename=chunk.filename,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                metadata=metadata,
            )
        )
    return expanded


def merge_neighbor_chunks(
    primary: list[RetrievedChunk],
    neighbors: Iterable[RetrievedChunk],
    *,
    limit: int,
) -> list[RetrievedChunk]:
    """Append neighbor context chunks without exceeding ``limit``."""

    by_id = {chunk.chunk_id: chunk for chunk in primary}
    ordered = list(primary)
    for neighbor in neighbors:
        if neighbor.chunk_id in by_id:
            continue
        metadata = dict(neighbor.metadata)
        metadata["neighbor_expansion"] = True
        merged = RetrievedChunk(
            chunk_id=neighbor.chunk_id,
            document_id=neighbor.document_id,
            content=neighbor.content,
            score=neighbor.score,
            filename=neighbor.filename,
            chunk_index=neighbor.chunk_index,
            page_number=neighbor.page_number,
            metadata=metadata,
        )
        by_id[neighbor.chunk_id] = merged
        ordered.append(merged)
        if len(ordered) >= limit:
            break
    return ordered[:limit]


def apply_quality_strategies(
    chunks: list[RetrievedChunk],
    *,
    options: QualityOptions,
    final_limit: int,
) -> list[RetrievedChunk]:
    """Apply enabled quality steps. Disabled options are no-ops (defaults unchanged)."""

    result = list(chunks)
    if options.parent_child_expand:
        result = expand_parent_content(result)
    if options.exact_dedup:
        result = exact_deduplicate(result)
    if options.near_dedup:
        result = near_deduplicate(result, threshold=options.near_dedup_threshold)
    if options.per_document_limit > 0:
        result = apply_per_document_limit(result, limit=options.per_document_limit)
    if options.mmr_enabled:
        result = mmr_select(result, limit=final_limit, lambda_mult=options.mmr_lambda)
    return result[:final_limit]
