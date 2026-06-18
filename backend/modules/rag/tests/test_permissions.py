import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService


class PermissionTest(unittest.IsolatedAsyncioTestCase):
    async def test_unauthorized_project_member_cannot_upload(self):
        db = AsyncMock()
        service = DocumentIngestionService(db)
        service.config = SimpleNamespace(
            enabled=True,
            max_file_bytes=1_000_000,
            allowed_file_types=("txt",),
        )
        service.policy = MagicMock()
        service.policy.is_allowed_file_type.return_value = True
        service.projects_repo = MagicMock()
        service.projects_repo.get_by_id_for_user = AsyncMock(return_value=None)
        service.storage = MagicMock()

        with self.assertRaises(HTTPException) as ctx:
            await service.upload_document(
                user_id="user-a",
                filename="x.txt",
                content=b"data",
                content_type="text/plain",
                project_id="proj-forbidden",
            )
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_user_cannot_delete_other_users_document(self):
        db = AsyncMock()
        service = DocumentIngestionService(db)
        service.config = SimpleNamespace(enabled=True)
        service.repo = MagicMock()
        service.repo.get_document = AsyncMock(
            return_value=SimpleNamespace(
                id="doc-b",
                user_id="user-b",
                storage_path=None,
            )
        )
        service.vector_store = MagicMock()
        service.storage = MagicMock()

        with self.assertRaises(HTTPException) as ctx:
            await service.delete_document(
                document_id="doc-b",
                user_id="user-a",
                is_admin=False,
            )
        self.assertEqual(ctx.exception.status_code, 403)
