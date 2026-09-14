"""Shared retrieval metrics for offline harness and online workbench."""

from __future__ import annotations

import math


def retrieval_metrics(
    ranked_ids: list[str],
    judgments: dict[str, int],
    k: int,
) -> dict[str, float]:
    """Compute Recall@K, Precision@K, MRR, and nDCG@K from graded judgments."""

    ranked = ranked_ids[:k]
    relevant = {chunk_id for chunk_id, grade in judgments.items() if grade > 0}
    hits = relevant.intersection(ranked)
    recall = len(hits) / len(relevant) if relevant else 1.0
    precision = len(hits) / len(ranked) if ranked else 0.0
    reciprocal_rank = next(
        (1.0 / rank for rank, chunk_id in enumerate(ranked, start=1) if chunk_id in relevant),
        0.0,
    )
    dcg = sum(
        ((2 ** judgments.get(chunk_id, 0)) - 1) / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked, start=1)
    )
    ideal_grades = sorted(judgments.values(), reverse=True)[:k]
    ideal_dcg = sum(
        ((2**grade) - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal_grades, start=1)
    )
    return {
        "recall_at_k": round(recall, 6),
        "precision_at_k": round(precision, 6),
        "mrr": round(reciprocal_rank, 6),
        "ndcg_at_k": round(dcg / ideal_dcg if ideal_dcg else 1.0, 6),
    }


def judgments_from_expected(
    *,
    expected_chunk_ids: list[str] | None = None,
    judgments: dict[str, int] | None = None,
) -> dict[str, int]:
    """Normalize case expectations into graded judgments."""

    merged: dict[str, int] = {}
    for chunk_id in expected_chunk_ids or []:
        merged[str(chunk_id)] = max(merged.get(str(chunk_id), 0), 1)
    for chunk_id, grade in (judgments or {}).items():
        merged[str(chunk_id)] = max(int(grade), merged.get(str(chunk_id), 0))
    return merged


def metric_deltas(
    baseline: dict[str, float],
    candidate: dict[str, float],
) -> dict[str, float]:
    keys = sorted(set(baseline) | set(candidate))
    return {
        key: round(float(candidate.get(key, 0.0)) - float(baseline.get(key, 0.0)), 6)
        for key in keys
    }
