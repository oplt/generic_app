from __future__ import annotations

from pathlib import Path

from backend.modules.rag.evaluation.harness import STRATEGIES, evaluate_dataset

DATASET = Path(__file__).parents[1] / "evaluation" / "golden_v1.json"


def test_golden_evaluation_is_deterministic_except_for_timings():
    first = evaluate_dataset(DATASET, top_k=3, iterations=2)
    second = evaluate_dataset(DATASET, top_k=3, iterations=2)

    for strategy in STRATEGIES:
        assert (
            first["strategies"][strategy]["aggregate"]
            == second["strategies"][strategy]["aggregate"]
        )
        assert first["strategies"][strategy]["cases"] == second["strategies"][strategy]["cases"]
    assert first["dataset"] == second["dataset"]
    assert tuple(first["strategies"]) == STRATEGIES


def test_golden_evaluation_reports_required_quality_and_cost_metrics():
    report = evaluate_dataset(DATASET, top_k=3, iterations=1)

    for strategy in STRATEGIES:
        aggregate = report["strategies"][strategy]["aggregate"]
        assert set(aggregate) == {
            "recall_at_k",
            "precision_at_k",
            "mrr",
            "ndcg_at_k",
            "citation_correctness",
        }
        assert aggregate["recall_at_k"] >= 0.8

    assert set(report["setup_performance_ms"]) == {
        "parse",
        "chunk",
        "embedding",
    }
    assert set(report["strategies"]["current_ranker"]["performance_ms"]) == {
        "retrieval",
        "rerank",
        "generation",
        "end_to_end",
    }
    assert report["usage"]["provider_cost_usd"] == 0.0
