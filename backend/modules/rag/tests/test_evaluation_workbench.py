"""Unit tests for RAG evaluation metrics and workbench helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.modules.rag.application.evaluation_service import RagEvaluationService
from backend.modules.rag.evaluation.judges import heuristic_generation_scores
from backend.modules.rag.evaluation.metrics import (
    judgments_from_expected,
    metric_deltas,
    retrieval_metrics,
)


class MetricsTest(unittest.TestCase):
    def test_retrieval_metrics_perfect_ranking(self) -> None:
        metrics = retrieval_metrics(
            ["a", "b", "c"],
            {"a": 2, "b": 1},
            k=3,
        )
        self.assertEqual(metrics["recall_at_k"], 1.0)
        self.assertGreater(metrics["mrr"], 0.9)
        self.assertGreater(metrics["ndcg_at_k"], 0.9)

    def test_judgments_merge_expected_ids(self) -> None:
        judgments = judgments_from_expected(
            expected_chunk_ids=["x", "y"],
            judgments={"y": 3, "z": 1},
        )
        self.assertEqual(judgments["x"], 1)
        self.assertEqual(judgments["y"], 3)
        self.assertEqual(judgments["z"], 1)

    def test_metric_deltas_report_regressions(self) -> None:
        deltas = metric_deltas(
            {"recall_at_k": 0.8, "mrr": 0.5},
            {"recall_at_k": 0.9, "mrr": 0.4},
        )
        self.assertEqual(deltas["recall_at_k"], 0.1)
        self.assertEqual(deltas["mrr"], -0.1)


class JudgesTest(unittest.TestCase):
    def test_heuristic_generation_scores_are_bounded(self) -> None:
        scores = heuristic_generation_scores(
            query="What is ZX-204?",
            answer="ZX-204 means expired invitation [Source 1]",
            context_chunks=["Error code ZX-204 means an invitation link has expired."],
            expected_facts=["expired"],
        )
        for value in scores.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        self.assertGreater(scores["groundedness"], 0.0)


class EvaluationTenantTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_dataset_hides_cross_tenant(self) -> None:
        db = MagicMock()
        service = RagEvaluationService(db)
        service.repo.get_dataset = AsyncMock(return_value=None)
        with self.assertRaises(Exception) as raised:
            await service.get_dataset(
                "ds-1", user_id="user-a", organization_id="org-a"
            )
        self.assertEqual(raised.exception.status_code, 404)
        service.repo.get_dataset.assert_awaited_once_with(
            "ds-1", user_id="user-a", organization_id="org-a"
        )

    async def test_run_dataset_persists_aggregate_and_comparison(self) -> None:
        db = MagicMock()
        db.flush = AsyncMock()
        service = RagEvaluationService(db)
        dataset = SimpleNamespace(id="ds-1")
        case = SimpleNamespace(
            id="case-1",
            question="ZX-204?",
            expected_chunk_ids_json=["exact"],
            judgments_json={},
            expected_facts_json=[],
        )
        baseline = SimpleNamespace(
            id="run-base",
            metrics_json={"recall_at_k": 0.5, "precision_at_k": 0.5, "mrr": 0.5, "ndcg_at_k": 0.5},
        )
        run = SimpleNamespace(
            id="run-1",
            dataset_id="ds-1",
            status="pending",
            metrics_json={},
            latency_json={},
            comparison_json=None,
            completed_at=None,
            error_message=None,
        )
        service.get_dataset = AsyncMock(return_value=dataset)
        service.repo.list_cases = AsyncMock(return_value=[case])
        service.repo.get_run = AsyncMock(return_value=baseline)
        service.repo.create_run = AsyncMock(return_value=run)
        service.repo.create_run_item = AsyncMock()
        service._retrieve_detailed = AsyncMock(
            return_value={
                "candidates": [
                    {
                        "chunk_id": "exact",
                        "content": "ZX-204 expired",
                        "document_id": "d1",
                    }
                ],
                "context_chunks": [
                    {"chunk_id": "exact", "content": "ZX-204 expired"}
                ],
                "latencies_ms": {
                    "embedding": 1.0,
                    "vector": 2.0,
                    "lexical": 3.0,
                    "fusion": 0.5,
                    "rerank": 0.2,
                    "context": 0.1,
                    "total": 7.0,
                },
            }
        )

        result = await service.run_dataset(
            "ds-1",
            user_id="user-a",
            organization_id="org-a",
            name="candidate",
            strategy="hybrid_rrf",
            top_k=3,
            baseline_run_id="run-base",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.metrics_json["recall_at_k"], 1.0)
        self.assertIsNotNone(result.comparison_json)
        self.assertEqual(result.comparison_json["baseline_run_id"], "run-base")
        self.assertGreater(result.comparison_json["deltas"]["recall_at_k"], 0)
        service.repo.create_run_item.assert_awaited_once()


class ProbeCandidateShapeTest(unittest.IsolatedAsyncioTestCase):
    async def test_probe_returns_lane_ranks_without_generation(self) -> None:
        db = MagicMock()
        service = RagEvaluationService(db)
        service._retrieve_detailed = AsyncMock(
            return_value={
                "strategy": "hybrid_rrf",
                "top_k": 2,
                "candidates": [
                    {
                        "rank": 1,
                        "chunk_id": "c1",
                        "content": "hello",
                        "vector_rank": 1,
                        "lexical_rank": 2,
                        "included": True,
                    }
                ],
                "context_chunks": [{"chunk_id": "c1", "content": "hello"}],
                "assembled_context": "ctx",
                "latencies_ms": {
                    "embedding": 1,
                    "vector": 1,
                    "lexical": 1,
                    "fusion": 1,
                    "rerank": 0,
                    "context": 1,
                },
            }
        )
        result = await service.probe(
            user_id="u1",
            organization_id=None,
            query="hello",
            include_generation_judges=False,
        )
        self.assertEqual(result["candidates"][0]["vector_rank"], 1)
        self.assertIsNone(result["generation"]["scores"])
        self.assertIn("total", result["latencies_ms"])
