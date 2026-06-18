import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.modules.rag.infrastructure.pgvector_adapter import PgVectorAdapter, _cosine_similarity


def _chunk_row(
    *,
    chunk_id: str,
    document_id: str,
    user_id: str,
    content: str,
    embedding: list[float],
    project_id: str | None = None,
    chunk_index: int = 0,
):
    return SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        user_id=user_id,
        project_id=project_id,
        chunk_index=chunk_index,
        content=content,
        embedding_json=json.dumps(embedding),
        metadata_json=json.dumps({"page_number": chunk_index}),
    )


class RetrievalFilterTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = AsyncMock()
        self.config = SimpleNamespace(score_threshold=0.1, vector_backend="pgvector")
        self.adapter = PgVectorAdapter(self.db, self.config)
        self.adapter.repo = MagicMock()

    async def test_retrieval_filters_by_user_id(self):
        doc = SimpleNamespace(
            id="doc-a",
            user_id="user-a",
            original_filename="a.txt",
            project_id=None,
        )
        self.adapter.repo.list_indexed_documents = AsyncMock(return_value=[doc])
        self.adapter.repo.list_chunks_for_documents = AsyncMock(
            return_value=[
                _chunk_row(
                    chunk_id="c1",
                    document_id="doc-a",
                    user_id="user-a",
                    content="user a secret",
                    embedding=[1.0, 0.0],
                ),
                _chunk_row(
                    chunk_id="c2",
                    document_id="doc-b",
                    user_id="user-b",
                    content="user b secret",
                    embedding=[1.0, 0.0],
                ),
            ]
        )
        results = await self.adapter.similarity_search(
            "secret",
            user_id="user-a",
            project_id=None,
            top_k=5,
            query_embedding=[1.0, 0.0],
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, "c1")

    async def test_retrieval_filters_by_project_id(self):
        doc = SimpleNamespace(
            id="doc-p",
            user_id="user-a",
            original_filename="p.txt",
            project_id="proj-1",
        )
        self.adapter.repo.list_indexed_documents = AsyncMock(return_value=[doc])
        self.adapter.repo.list_chunks_for_documents = AsyncMock(
            return_value=[
                _chunk_row(
                    chunk_id="c1",
                    document_id="doc-p",
                    user_id="user-a",
                    project_id="proj-1",
                    content="project one",
                    embedding=[1.0, 0.0],
                ),
                _chunk_row(
                    chunk_id="c2",
                    document_id="doc-p",
                    user_id="user-a",
                    project_id="proj-2",
                    content="project two",
                    embedding=[1.0, 0.0],
                ),
            ]
        )
        results = await self.adapter.similarity_search(
            "project",
            user_id="user-a",
            project_id="proj-1",
            top_k=5,
            query_embedding=[1.0, 0.0],
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content, "project one")

    async def test_deleted_document_not_in_indexed_list(self):
        self.adapter.repo.list_indexed_documents = AsyncMock(return_value=[])
        results = await self.adapter.similarity_search(
            "query",
            user_id="user-a",
            project_id=None,
            top_k=5,
            query_embedding=[1.0, 0.0],
        )
        self.assertEqual(results, [])

    async def test_vector_unavailable_returns_empty(self):
        from backend.modules.rag.infrastructure.pgvector_adapter import QdrantAdapter

        adapter = QdrantAdapter()
        results = await adapter.similarity_search(
            query="q",
            user_id="u",
            project_id=None,
            top_k=5,
        )
        self.assertEqual(results, [])


class CosineSimilarityTest(unittest.TestCase):
    def test_identical_vectors_score_high(self):
        score = _cosine_similarity([1.0, 0.0], [1.0, 0.0])
        self.assertAlmostEqual(score, 1.0)
