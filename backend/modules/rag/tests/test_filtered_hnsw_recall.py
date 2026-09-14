"""Unit and optional live tests for filtered HNSW recall measurement."""

from __future__ import annotations

import unittest

from backend.modules.rag.evaluation.filtered_hnsw import (
    classify_plan,
    parse_pgvector_version,
    plan_uses_embedding_hnsw,
    recall_at_k,
    recommend_settings,
    supports_iterative_scan,
    unit_vector,
)
from backend.tests.integration_support import (
    ensure_integration_schema,
    integration_enabled,
    prepare_integration_runtime,
    rag_integration_ready,
)


class FilteredHnswHelpersTest(unittest.TestCase):
    def test_recall_at_k_is_fraction_of_exact_topk(self) -> None:
        exact = ["a", "b", "c", "d", "e"]
        self.assertEqual(recall_at_k(exact, ["a", "c", "x"], 5), 0.4)
        self.assertEqual(recall_at_k(exact, exact, 5), 1.0)
        self.assertEqual(recall_at_k([], ["a"], 5), 1.0)

    def test_unit_vectors_are_normalized_and_seeded(self) -> None:
        left = unit_vector(primary=0.9, seed=7, jitter=0.01)
        right = unit_vector(primary=0.9, seed=7, jitter=0.01)
        other = unit_vector(primary=0.2, seed=7, jitter=0.01)
        self.assertEqual(left, right)
        self.assertNotEqual(left, other)
        norm = sum(value * value for value in left) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_pgvector_version_parsing_and_iterative_scan_gate(self) -> None:
        self.assertEqual(parse_pgvector_version("0.6.2"), (0, 6, 2))
        self.assertFalse(supports_iterative_scan((0, 6, 2)))
        self.assertTrue(supports_iterative_scan((0, 7, 0)))

    def test_plan_classification_ignores_fixture_id_false_positives(self) -> None:
        btree_plan = (
            "Limit\n"
            "  ->  Sort\n"
            "        ->  Index Scan using ix_rag_chunks_user_project_document "
            "on rag_chunks c\n"
            "              Index Cond: ((user_id)::text = 'fhr-user-abc'::text)\n"
        )
        hnsw_plan = (
            "Limit\n"
            "  ->  Index Scan using ix_rag_chunks_embedding_hnsw on rag_chunks\n"
            "        Order By: (embedding <=> '[1,0,...]'::vector)\n"
        )
        self.assertFalse(plan_uses_embedding_hnsw(btree_plan))
        self.assertEqual(classify_plan(btree_plan), "filter_then_sort")
        self.assertTrue(plan_uses_embedding_hnsw(hnsw_plan))
        self.assertEqual(classify_plan(hnsw_plan), "embedding_hnsw")

    def test_recommend_settings_keeps_defaults_when_filter_then_sort_is_perfect(self) -> None:
        results = [
            {
                "default_trial": {
                    "recall_at_k": 1.0,
                    "ann_uses_embedding_hnsw": False,
                    "ann_latency_ms": 1.0,
                    "candidate_multiplier": 1,
                    "ef_search": None,
                    "iterative_scan": None,
                },
                "postfilter_trial": {"recall_at_k": 0.0},
                "trials": [
                    {
                        "mode": "production",
                        "candidate_multiplier": 1,
                        "ef_search": None,
                        "iterative_scan": None,
                        "recall_at_k": 1.0,
                        "ann_latency_ms": 1.0,
                    },
                    {
                        "mode": "production",
                        "candidate_multiplier": 3,
                        "ef_search": 100,
                        "iterative_scan": None,
                        "recall_at_k": 1.0,
                        "ann_latency_ms": 2.0,
                    },
                ],
            }
        ]
        recommendation = recommend_settings(
            results,
            {"hnsw_iterative_scan_supported": False},
        )
        self.assertEqual(recommendation["default_mean_recall_at_k"], 1.0)
        self.assertEqual(recommendation["production_plans_using_embedding_hnsw"], 0)
        self.assertEqual(recommendation["chosen"]["ef_search"], None)
        self.assertIn("Leave hnsw.ef_search unset", recommendation["rationale"])


@unittest.skipUnless(
    integration_enabled() and rag_integration_ready(),
    "Set RUN_INTEGRATION_TESTS=1 with migrated PostgreSQL",
)
class FilteredHnswIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_live_benchmark_reports_versions_plans_and_postfilter_gap(self) -> None:
        self.assertTrue(await ensure_integration_schema())
        await prepare_integration_runtime()

        from backend.modules.rag.evaluation.filtered_hnsw import run_benchmark

        report = await run_benchmark(
            top_k=5,
            noise_chunks=120,
            target_relevant=5,
            target_filler=10,
            candidate_multipliers=(1, 3),
            ef_search_values=(None, 40),
            postfilter_overfetch=80,
        )

        self.assertEqual(report["benchmark"], "filtered-hnsw-recall-v1")
        self.assertIsNotNone(report["runtime"]["postgresql_version"])
        self.assertIsNotNone(report["runtime"]["pgvector_version"])
        self.assertIsNotNone(report["runtime"]["hnsw_indexdef"])
        self.assertEqual(len(report["filters"]), 5)
        for result in report["filters"]:
            self.assertIn(
                result["filter"],
                {"user", "organization", "project", "document", "source"},
            )
            self.assertIsNotNone(result["default_trial"])
            self.assertIn("plan_class", result["default_trial"])
            self.assertIn("ann_plan", result["default_trial"])
            self.assertLessEqual(result["postfilter_trial"]["recall_at_k"], 1.0)
        self.assertIn("chosen", report["recommendation"])
        self.assertIn("rationale", report["recommendation"])


if __name__ == "__main__":
    unittest.main()
