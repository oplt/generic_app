from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.lib.vectors import cosine_similarity, estimate_tokens
from backend.modules.rag.application.retrieval_ranker import (
    HybridRetrievalRanker,
    reciprocal_rank_fuse,
)
from backend.modules.rag.application.quality_strategies import (
    apply_quality_strategies,
    QualityOptions,
)
from backend.modules.rag.evaluation.metrics import retrieval_metrics
from backend.modules.rag.domain.models import RetrievedChunk

EVALUATION_VERSION = "rag-offline-v1"
STRATEGIES = (
    "vector_only",
    "current_ranker",
    "independent_hybrid",
    "hybrid_exact_dedup",
    "hybrid_mmr",
)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class _Chunk:
    chunk_id: str
    document_id: str
    filename: str
    content: str


def _tokens(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _embedding(text: str, dimensions: int = 256) -> list[float]:
    """Stable feature-hashed bag-of-words embedding for an offline baseline."""
    values = [0.0] * dimensions
    for token, count in Counter(_tokens(text)).items():
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        values[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples) or [0.0]

    def nearest_rank(percentile: float) -> float:
        index = max(0, math.ceil(percentile * len(ordered)) - 1)
        return round(ordered[index], 4)

    return {"p50": nearest_rank(0.50), "p95": nearest_rank(0.95), "p99": nearest_rank(0.99)}


def _lexical_score(query: str, content: str) -> float:
    query_terms = set(_tokens(query))
    if not query_terms:
        return 0.0
    return len(query_terms.intersection(_tokens(content))) / len(query_terms)


def _vector_ranking(
    query: str,
    chunks: list[_Chunk],
    embeddings: dict[str, list[float]],
) -> list[RetrievedChunk]:
    query_embedding = _embedding(query)
    ranked = [
        RetrievedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            content=chunk.content,
            score=cosine_similarity(query_embedding, embeddings[chunk.chunk_id]),
            filename=chunk.filename,
            chunk_index=0,
            metadata={"lexical_score": _lexical_score(query, chunk.content)},
        )
        for chunk in chunks
    ]
    return sorted(ranked, key=lambda item: (-item.score, item.chunk_id))


def _independent_hybrid(
    query: str,
    chunks: list[_Chunk],
    embeddings: dict[str, list[float]],
) -> list[RetrievedChunk]:
    vector_ranked = _vector_ranking(query, chunks, embeddings)
    lexical_ranked = [
        RetrievedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            content=chunk.content,
            score=_lexical_score(query, chunk.content),
            filename=chunk.filename,
            chunk_index=0,
            metadata={"lexical_score": _lexical_score(query, chunk.content)},
        )
        for chunk in chunks
    ]
    lexical_ranked.sort(key=lambda item: (-item.score, item.chunk_id))
    return reciprocal_rank_fuse([vector_ranked, lexical_ranked], limit=len(chunks))


def _rank(
    strategy: str,
    query: str,
    chunks: list[_Chunk],
    embeddings: dict[str, list[float]],
    *,
    top_k: int,
) -> tuple[list[RetrievedChunk], float, float]:
    started = time.perf_counter_ns()
    vector_ranked = _vector_ranking(query, chunks, embeddings)
    retrieval_ms = (time.perf_counter_ns() - started) / 1_000_000
    rerank_started = time.perf_counter_ns()
    if strategy == "vector_only":
        ranked = vector_ranked
    elif strategy == "current_ranker":
        candidate_limit = min(len(vector_ranked), top_k * 3)
        ranked = HybridRetrievalRanker().rerank(query, vector_ranked[:candidate_limit], limit=top_k)
    elif strategy == "hybrid_exact_dedup":
        ranked = apply_quality_strategies(
            _independent_hybrid(query, chunks, embeddings),
            options=QualityOptions(exact_dedup=True),
            final_limit=top_k,
        )
    elif strategy == "hybrid_mmr":
        ranked = apply_quality_strategies(
            _independent_hybrid(query, chunks, embeddings),
            options=QualityOptions(mmr_enabled=True, mmr_lambda=0.7),
            final_limit=top_k,
        )
    else:
        ranked = _independent_hybrid(query, chunks, embeddings)
    rerank_ms = (time.perf_counter_ns() - rerank_started) / 1_000_000
    return ranked[:top_k], retrieval_ms, rerank_ms


def _mean_metrics(case_results: list[dict[str, Any]]) -> dict[str, float]:
    names = ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k", "citation_correctness")
    return {
        name: round(statistics.fmean(case["metrics"][name] for case in case_results), 6)
        for name in names
    }


def evaluate_dataset(
    dataset_path: Path,
    *,
    top_k: int = 3,
    iterations: int = 25,
) -> dict[str, Any]:
    if top_k < 1 or iterations < 1:
        raise ValueError("top_k and iterations must be positive")

    setup_samples: dict[str, list[float]] = {stage: [] for stage in ("parse", "chunk", "embedding")}
    raw_bytes = b""
    dataset: dict[str, Any] = {}
    chunks: list[_Chunk] = []
    embeddings: dict[str, list[float]] = {}
    for _ in range(iterations):
        parse_started = time.perf_counter_ns()
        raw_bytes = dataset_path.read_bytes()
        dataset = json.loads(raw_bytes)
        setup_samples["parse"].append((time.perf_counter_ns() - parse_started) / 1_000_000)

        chunk_started = time.perf_counter_ns()
        chunks = [
            _Chunk(
                chunk_id=chunk["id"],
                document_id=document["id"],
                filename=document["title"],
                content=chunk["text"],
            )
            for document in dataset["documents"]
            for chunk in document["chunks"]
        ]
        setup_samples["chunk"].append((time.perf_counter_ns() - chunk_started) / 1_000_000)

        embedding_started = time.perf_counter_ns()
        embeddings = {chunk.chunk_id: _embedding(chunk.content) for chunk in chunks}
        setup_samples["embedding"].append((time.perf_counter_ns() - embedding_started) / 1_000_000)

    strategy_results: dict[str, Any] = {}
    generation_input_tokens = 0
    generation_output_tokens = 0
    for strategy in STRATEGIES:
        cases: list[dict[str, Any]] = []
        strategy_samples: dict[str, list[float]] = {
            stage: [] for stage in ("retrieval", "rerank", "generation", "end_to_end")
        }
        for case in dataset["queries"]:
            final_ranked: list[RetrievedChunk] = []
            for _ in range(iterations):
                end_started = time.perf_counter_ns()
                ranked, retrieval_ms, rerank_ms = _rank(
                    strategy,
                    case["query"],
                    chunks,
                    embeddings,
                    top_k=top_k,
                )
                generation_started = time.perf_counter_ns()
                answer = f"{ranked[0].content} [Source 1]" if ranked else "No context found."
                generation_ms = (time.perf_counter_ns() - generation_started) / 1_000_000
                strategy_samples["retrieval"].append(retrieval_ms)
                strategy_samples["rerank"].append(rerank_ms)
                strategy_samples["generation"].append(generation_ms)
                strategy_samples["end_to_end"].append(
                    (time.perf_counter_ns() - end_started) / 1_000_000
                )
                final_ranked = ranked

            ranked_ids = [chunk.chunk_id for chunk in final_ranked]
            metrics = retrieval_metrics(ranked_ids, case["judgments"], top_k)
            metrics["citation_correctness"] = round(
                1.0 if ranked_ids and ranked_ids[0] in case["judgments"] else 0.0,
                6,
            )
            generation_input_tokens += estimate_tokens(
                case["query"] + "\n" + "\n".join(chunk.content for chunk in final_ranked)
            )
            generation_output_tokens += estimate_tokens(answer)
            cases.append(
                {"case_id": case["id"], "ranked_chunk_ids": ranked_ids, "metrics": metrics}
            )
        strategy_results[strategy] = {
            "aggregate": _mean_metrics(cases),
            "cases": cases,
            "performance_ms": {
                stage: _percentiles(values) for stage, values in strategy_samples.items()
            },
        }

    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset": {
            "id": dataset["dataset_id"],
            "schema_version": dataset["schema_version"],
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "documents": len(dataset["documents"]),
            "chunks": len(chunks),
            "queries": len(dataset["queries"]),
        },
        "configuration": {
            "top_k": top_k,
            "iterations": iterations,
            "embedding": "deterministic-feature-hash-256",
            "generation": "deterministic-top-chunk-extractive",
        },
        "strategies": strategy_results,
        "setup_performance_ms": {
            stage: _percentiles(values) for stage, values in setup_samples.items()
        },
        "usage": {
            "embedding_tokens": sum(estimate_tokens(chunk.content) for chunk in chunks),
            "generation_input_tokens": generation_input_tokens,
            "generation_output_tokens": generation_output_tokens,
            "provider_cost_usd": 0.0,
        },
    }


def _human_summary(report: dict[str, Any]) -> str:
    lines = [
        f"RAG evaluation: {report['dataset']['id']} ({report['evaluation_version']})",
        (
            f"top_k={report['configuration']['top_k']} "
            f"iterations={report['configuration']['iterations']}"
        ),
        "strategy             Recall@K  Precision@K  MRR     nDCG@K  Citation",
    ]
    for strategy in STRATEGIES:
        metrics = report["strategies"][strategy]["aggregate"]
        lines.append(
            f"{strategy:<20} {metrics['recall_at_k']:<9.3f} {metrics['precision_at_k']:<12.3f} "
            f"{metrics['mrr']:<7.3f} {metrics['ndcg_at_k']:<7.3f} "
            f"{metrics['citation_correctness']:.3f}"
        )
    lines.append("setup latency ms        P50       P95       P99")
    for stage, percentiles in report["setup_performance_ms"].items():
        lines.append(
            f"{stage:<23} {percentiles['p50']:<9.4f} {percentiles['p95']:<9.4f} "
            f"{percentiles['p99']:.4f}"
        )
    lines.append("strategy end-to-end ms P50       P95       P99")
    for strategy in STRATEGIES:
        percentiles = report["strategies"][strategy]["performance_ms"]["end_to_end"]
        lines.append(
            f"{strategy:<23} {percentiles['p50']:<9.4f} {percentiles['p95']:<9.4f} "
            f"{percentiles['p99']:.4f}"
        )
    usage = report["usage"]
    lines.append(
        "tokens embedding/input/output="
        f"{usage['embedding_tokens']}/{usage['generation_input_tokens']}/"
        f"{usage['generation_output_tokens']}; provider cost=${usage['provider_cost_usd']:.4f}"
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    default_dataset = Path(__file__).with_name("golden_v1.json")
    parser = argparse.ArgumentParser(description="Run the offline deterministic RAG baseline")
    parser.add_argument("--dataset", type=Path, default=default_dataset)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = evaluate_dataset(args.dataset, top_k=args.top_k, iterations=args.iterations)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(_human_summary(report))
    print(f"machine-readable report: {args.json_output}")
    return 0
