import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.lib.vector_search import (
    pgvector_readiness,
    reset_pgvector_readiness_cache,
)
from backend.lib.vectors import cosine_similarity


class PgVectorReadinessTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_pgvector_readiness_cache()

    async def test_readiness_requires_extension_column_and_hnsw_index(self):
        db = AsyncMock()
        db.bind = None
        result = MagicMock()
        result.mappings.return_value.one.return_value = {
            "extension_available": True,
            "embedding_column_available": True,
            "hnsw_index_available": False,
        }
        db.execute.return_value = result

        readiness = await pgvector_readiness(db)

        self.assertFalse(readiness.available)
        self.assertEqual(readiness.reason, "hnsw_index_missing")
        self.assertEqual(db.execute.await_count, 1)

    async def test_ready_result_is_cached_briefly(self):
        db = AsyncMock()
        db.bind = None
        result = MagicMock()
        result.mappings.return_value.one.return_value = {
            "extension_available": True,
            "embedding_column_available": True,
            "hnsw_index_available": True,
        }
        db.execute.return_value = result

        first = await pgvector_readiness(db)
        second = await pgvector_readiness(db)

        self.assertTrue(first.available)
        self.assertTrue(second.available)
        self.assertEqual(db.execute.await_count, 1)


class CosineSimilarityTest(unittest.TestCase):
    def test_identical_vectors_score_high(self):
        score = cosine_similarity([1.0, 0.0], [1.0, 0.0])
        self.assertAlmostEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
