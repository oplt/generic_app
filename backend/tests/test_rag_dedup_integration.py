from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import func, select

from backend.lib.project_access import AuthorizedOwnershipScope
from backend.modules.identity_access.models import Organization, User
from backend.modules.rag.infrastructure.models import RagDocument, RagIngestionJob
from backend.tests.integration_support import (
    ensure_integration_schema,
    integration_enabled,
    prepare_integration_runtime,
    unique_email,
)


class BarrierStorage:
    def __init__(self, barrier: asyncio.Barrier) -> None:
        self.barrier = barrier
        self.deleted: list[str] = []

    async def store_document(self, **kwargs: str) -> str:
        await self.barrier.wait()
        return kwargs["object_key"]

    async def delete_document(self, storage_path: str | None) -> None:
        if storage_path is not None:
            self.deleted.append(storage_path)


@unittest.skipUnless(
    integration_enabled(),
    "Set RUN_INTEGRATION_TESTS=1 with migrated PostgreSQL",
)
class RagDedupIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_identical_uploads_create_one_document_and_job(self) -> None:
        self.assertTrue(await ensure_integration_schema())
        await prepare_integration_runtime()
        from backend.db.session import SessionLocal
        from backend.modules.rag.application.document_ingestion_service import (
            DocumentIngestionService,
        )

        user_id = str(uuid4())
        organization_id = str(uuid4())
        async with SessionLocal() as db:
            db.add_all(
                [
                    User(
                        id=user_id,
                        email=unique_email("rag-dedup"),
                        password_hash="test",
                    ),
                    Organization(id=organization_id, name="RAG dedup test"),
                ]
            )
            await db.commit()

        barrier = asyncio.Barrier(10)
        storage = BarrierStorage(barrier)

        async def run_upload():
            async with SessionLocal() as db:
                service = DocumentIngestionService(db)
                service.storage = storage
                service.policy = MagicMock()
                service.policy.is_allowed_file_type.return_value = True
                service.policy.detect_content_type.return_value = "text/plain"
                service._scan_or_reject = AsyncMock()
                service.project_access = MagicMock()
                service.project_access.resolve_ownership_scope = AsyncMock(
                    return_value=AuthorizedOwnershipScope(
                        user_id=user_id,
                        organization_id=organization_id,
                    )
                )
                return await service.upload_document(
                    user_id=user_id,
                    filename="same.txt",
                    content=b"identical upload content",
                    content_type="text/plain",
                )

        with (
            patch(
                "backend.modules.rag.application.document_ingestion_service.enqueue_job_event",
                new=AsyncMock(),
            ),
            patch(
                "backend.modules.rag.application.document_ingestion_service.queue_document_indexing",
            ),
        ):
            results = await asyncio.gather(*(run_upload() for _ in range(10)))

        self.assertEqual({result.document.id for result in results}, {results[0].document.id})
        self.assertEqual(sum(result.duplicate for result in results), 9)
        self.assertEqual(len(storage.deleted), 9)

        async with SessionLocal() as db:
            self.assertEqual(
                await db.scalar(
                    select(func.count())
                    .select_from(RagDocument)
                    .where(RagDocument.user_id == user_id)
                ),
                1,
            )
            self.assertEqual(
                await db.scalar(
                    select(func.count())
                    .select_from(RagIngestionJob)
                    .where(RagIngestionJob.user_id == user_id)
                ),
                1,
            )
