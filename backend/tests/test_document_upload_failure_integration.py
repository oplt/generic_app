from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import func, select

from backend.modules.identity_access.models import User
from backend.modules.rag.infrastructure.models import RagDocument, RagIngestionJob
from backend.tests.integration_support import (
    ensure_integration_schema,
    integration_enabled,
    prepare_integration_runtime,
    unique_email,
)


@unittest.skipUnless(
    integration_enabled(),
    "Set RUN_INTEGRATION_TESTS=1 with migrated PostgreSQL",
)
class DocumentUploadFailureIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_database_failure_compensates_uploaded_object(self) -> None:
        self.assertTrue(await ensure_integration_schema())
        await prepare_integration_runtime()
        from backend.db.session import SessionLocal
        from backend.lib.project_access import AuthorizedOwnershipScope
        from backend.modules.rag.application.document_ingestion_service import (
            DocumentIngestionService,
        )

        user_id = str(uuid4())
        async with SessionLocal() as db:
            db.add(User(id=user_id, email=unique_email("upload-failure"), password_hash="test"))
            await db.commit()

        storage = MagicMock()
        storage.store_document = AsyncMock(return_value="rag/fault-injection")
        storage.delete_document = AsyncMock()

        db = SessionLocal()
        try:
            service = DocumentIngestionService(db)
            service.storage = storage
            service.policy = MagicMock()
            service.policy.is_allowed_file_type.return_value = True
            service.policy.detect_content_type.return_value = "text/plain"
            service._scan_or_reject = AsyncMock()
            service.project_access = MagicMock()
            service.project_access.resolve_ownership_scope = AsyncMock(
                return_value=AuthorizedOwnershipScope(user_id=user_id, organization_id=None)
            )
            service.repo.create_document = AsyncMock(side_effect=RuntimeError("insert failure"))

            with patch(
                "backend.modules.rag.application.document_ingestion_service.enqueue_job_event",
                new=AsyncMock(),
            ), self.assertRaises(RuntimeError):
                await service.upload_document(
                    user_id=user_id,
                    filename="notes.txt",
                    content=b"hello",
                    content_type="text/plain",
                )
        finally:
            await db.close()

        storage.delete_document.assert_awaited_once_with("rag/fault-injection")
        async with SessionLocal() as db:
            self.assertEqual(
                await db.scalar(
                    select(func.count())
                    .select_from(RagDocument)
                    .where(RagDocument.user_id == user_id)
                ),
                0,
            )
            self.assertEqual(
                await db.scalar(
                    select(func.count())
                    .select_from(RagIngestionJob)
                    .where(RagIngestionJob.user_id == user_id)
                ),
                0,
            )
