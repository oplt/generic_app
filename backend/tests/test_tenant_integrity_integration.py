from __future__ import annotations

import unittest
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from backend.modules.chat.models import ChatConversation
from backend.modules.identity_access.models import Organization, User
from backend.modules.projects.models import Project
from backend.modules.rag.infrastructure.models import (
    RagChunk,
    RagDocument,
    RagIngestionJob,
    RagQueryRecord,
)
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
class TenantIntegrityIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_scope_constraints_and_delete_policies(self) -> None:
        self.assertTrue(await ensure_integration_schema())
        await prepare_integration_runtime()
        from backend.db.session import SessionLocal

        user = User(
            id=str(uuid4()),
            email=unique_email("tenant-integrity"),
            password_hash="test",
        )
        organization = Organization(
            id=str(uuid4()), name=f"Tenant integrity {uuid4().hex[:8]}"
        )
        project = Project(
            id=str(uuid4()),
            owner_id=user.id,
            organization_id=organization.id,
            name="Scoped project",
        )
        other_project = Project(
            id=str(uuid4()),
            owner_id=user.id,
            organization_id=organization.id,
            name="Other scoped project",
        )
        document = RagDocument(
            id=str(uuid4()),
            user_id=user.id,
            organization_id=organization.id,
            project_id=project.id,
            filename="fixture.txt",
            original_filename="fixture.txt",
            content_type="text/plain",
        )
        chunk = RagChunk(
            id=str(uuid4()),
            document_id=document.id,
            user_id=user.id,
            organization_id=organization.id,
            project_id=project.id,
            chunk_index=0,
            content="fixture",
        )
        job = RagIngestionJob(
            id=str(uuid4()),
            document_id=document.id,
            user_id=user.id,
            project_id=project.id,
        )
        query = RagQueryRecord(
            id=str(uuid4()),
            user_id=user.id,
            organization_id=organization.id,
            project_id=project.id,
            query="fixture?",
            answer="fixture",
            model_name="test",
        )
        conversation = ChatConversation(
            id=str(uuid4()),
            user_id=user.id,
            organization_id=organization.id,
            project_id=project.id,
        )

        async with SessionLocal() as db:
            db.add_all([user, organization])
            await db.commit()
            db.add_all([project, other_project])
            await db.commit()
            db.add_all([document, query, conversation])
            await db.commit()
            db.add_all([chunk, job])
            await db.commit()

        invalid_rows = (
            RagDocument(
                user_id=user.id,
                organization_id="missing-organization",
                project_id=project.id,
                filename="invalid.txt",
                original_filename="invalid.txt",
                content_type="text/plain",
            ),
            RagQueryRecord(
                user_id=user.id,
                organization_id=organization.id,
                project_id="missing-project",
                query="invalid?",
                answer="invalid",
                model_name="test",
            ),
            ChatConversation(
                user_id=user.id,
                organization_id="missing-organization",
                project_id=project.id,
            ),
            RagChunk(
                document_id=document.id,
                user_id=user.id,
                organization_id=organization.id,
                project_id=other_project.id,
                chunk_index=1,
                content="wrong project",
            ),
            RagIngestionJob(
                document_id=document.id,
                user_id=user.id,
                project_id=other_project.id,
            ),
        )
        for invalid_row in invalid_rows:
            async with SessionLocal() as db:
                db.add(invalid_row)
                with self.assertRaises(IntegrityError):
                    await db.commit()
                await db.rollback()

        async with SessionLocal() as db:
            stored_organization = await db.get(Organization, organization.id)
            await db.delete(stored_organization)
            with self.assertRaises(IntegrityError):
                await db.commit()
            await db.rollback()

        async with SessionLocal() as db:
            stored_project = await db.get(Project, project.id)
            await db.delete(stored_project)
            await db.commit()

        async with SessionLocal() as db:
            for model, row_id in (
                (RagDocument, document.id),
                (RagChunk, chunk.id),
                (RagIngestionJob, job.id),
                (RagQueryRecord, query.id),
                (ChatConversation, conversation.id),
            ):
                stored = await db.get(model, row_id)
                self.assertIsNone(stored.project_id)

            stored_document = await db.get(RagDocument, document.id)
            await db.delete(stored_document)
            await db.commit()

        async with SessionLocal() as db:
            chunk_count = await db.scalar(
                select(text("count(*)")).select_from(RagChunk).where(
                    RagChunk.document_id == document.id
                )
            )
            job_count = await db.scalar(
                select(text("count(*)")).select_from(RagIngestionJob).where(
                    RagIngestionJob.document_id == document.id
                )
            )
            self.assertEqual(chunk_count, 0)
            self.assertEqual(job_count, 0)
