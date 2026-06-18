import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.modules.rag.application.chunking_service import ChunkingService
from backend.modules.rag.application.document_parser_service import DocumentParserService
from backend.modules.rag.domain.enums import DocumentStatus
from backend.modules.rag.domain.models import ParsedDocument


class IngestionParserTest(unittest.IsolatedAsyncioTestCase):
    async def test_parse_txt_creates_content(self):
        parser = DocumentParserService()
        docs = await parser.parse_bytes(
            content=b"User prefers PostgreSQL for project X.",
            filename="notes.txt",
            content_type="text/plain",
        )
        self.assertEqual(len(docs), 1)
        self.assertIn("PostgreSQL", docs[0].content)

    def test_chunking_creates_indexed_chunks(self):
        config = SimpleNamespace(chunk_size=50, chunk_overlap=10)
        chunker = ChunkingService(config)
        docs = [ParsedDocument(content="A" * 120, metadata={})]

        async def run():
            return await chunker.chunk(
                docs,
                document_id="doc-1",
                user_id="user-a",
                filename="test.txt",
            )

        import asyncio

        chunks = asyncio.run(run())
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["document_id"], "doc-1")
        self.assertEqual(chunks[0].metadata["user_id"], "user-a")


class UploadCreatesDocumentTest(unittest.IsolatedAsyncioTestCase):
    @patch("backend.modules.rag.application.document_ingestion_service.RagPolicyService")
    @patch("backend.modules.rag.application.document_ingestion_service.FileStorageAdapter")
    async def test_upload_creates_document_row(self, storage_cls, policy_cls):
        policy_cls.return_value.is_allowed_file_type.return_value = True
        storage_cls.return_value.store_document = AsyncMock(return_value="rag/key")

        db = AsyncMock()
        service = __import__(
            "backend.modules.rag.application.document_ingestion_service",
            fromlist=["DocumentIngestionService"],
        ).DocumentIngestionService(db)
        service.config = SimpleNamespace(
            enabled=True,
            max_file_bytes=1_000_000,
            allowed_file_types=("txt",),
        )
        service.repo = MagicMock()
        doc = SimpleNamespace(id="doc-1", status=DocumentStatus.UPLOADED.value)
        job = SimpleNamespace(id="job-1")
        service.repo.create_document = AsyncMock(return_value=doc)
        service.repo.create_ingestion_job = AsyncMock(return_value=job)
        service.projects_repo = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        document, job_result, content = await service.upload_document(
            user_id="user-a",
            filename="notes.txt",
            content=b"hello world content",
            content_type="text/plain",
        )
        self.assertEqual(document.id, "doc-1")
        self.assertEqual(content, b"hello world content")
        service.repo.create_document.assert_awaited_once()


class EmbeddingAdapterTest(unittest.IsolatedAsyncioTestCase):
    @patch("backend.modules.rag.infrastructure.langchain_embeddings.AiProviderRegistry")
    async def test_embeddings_created_through_adapter(self, registry_cls):
        registry_cls.return_value.get.return_value.embed_texts = AsyncMock(
            return_value=[[0.1, 0.2], [0.3, 0.4]]
        )
        from backend.modules.rag.application.embedding_service import EmbeddingService

        service = EmbeddingService(
            SimpleNamespace(embedding_provider="local", embedding_model="test")
        )
        vectors = await service.embed_texts(["a", "b"])
        self.assertEqual(len(vectors), 2)
