import asyncio
import unittest
import uuid

from fastapi import HTTPException
from sqlalchemy import select

from backend.tests.integration_support import (
    api_client,
    auth_request,
    ensure_integration_schema,
    integration_enabled,
    register_and_sign_in,
)


@unittest.skipUnless(
    integration_enabled() and __import__("asyncio").run(ensure_integration_schema()),
    "Set RUN_INTEGRATION_TESTS=1 and provide PostgreSQL/Redis/Celery services",
)
class ReliabilityIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_auth_cookies_and_csrf_contract(self):
        async with api_client() as client:
            email = await register_and_sign_in(client)
            self.assertTrue(client.cookies.get("refresh_token"))
            response = await client.post("/api/v1/auth/logout")
            self.assertEqual(response.status_code, 403)
            self.assertIn("CSRF", response.json()["detail"])
            csrf = client.cookies.get("csrf_token")
            response = await client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(response.status_code, 204)
            self.assertFalse(client.cookies.get("refresh_token"))
            self.assertTrue(email)

    async def test_real_rag_upload_and_retrieval_path(self):
        async with api_client() as client:
            await register_and_sign_in(client)
            upload = await auth_request(
                client,
                "POST",
                "/api/v1/rag/documents/upload",
                files={
                    "file": (
                        f"reliability-{uuid.uuid4().hex}.txt",
                        b"PostgreSQL uses pgvector for semantic retrieval.",
                        "text/plain",
                    )
                },
            )
            self.assertEqual(upload.status_code, 201, upload.text)
            document_id = upload.json()["document"]["id"]
            retrieval = await auth_request(
                client,
                "POST",
                "/api/v1/rag/retrieve",
                json={"query": "What powers semantic retrieval?", "document_ids": [document_id]},
            )
            self.assertEqual(retrieval.status_code, 200, retrieval.text)

    async def test_real_redis_rate_limit_has_ttl_and_enforces_window(self):
        from backend.core.rate_limit import check_rate_limit, clear_rate_limit

        key = f"rate:integration:{uuid.uuid4().hex}"
        try:
            await check_rate_limit(key, 1, 60)
            with self.assertRaises(HTTPException) as context:
                await check_rate_limit(key, 1, 60)
            self.assertEqual(context.exception.status_code, 429)
        finally:
            await clear_rate_limit(key)

    async def test_celery_job_state_is_persisted(self):
        from backend.db.session import SessionLocal
        from backend.workers.job_service import run_tracked_sync
        from backend.workers.models import ApplicationJob

        correlation_id = f"integration-job:{uuid.uuid4().hex}"
        await asyncio.to_thread(
            run_tracked_sync,
            job_type="integration-test",
            payload={"secret": "not persisted"},
            runner=lambda: None,
            correlation_id=correlation_id,
        )
        async with SessionLocal() as db:
            job = (
                await db.execute(
                    select(ApplicationJob).where(ApplicationJob.correlation_id == correlation_id)
                )
            ).scalar_one()
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.payload["field_names"], ["secret"])

    async def test_object_storage_private_upload_path(self):
        from backend.core.config import settings
        from backend.core.storage import object_storage

        if not settings.STORAGE_BUCKET:
            self.skipTest("STORAGE_BUCKET is not configured")
        key = f"integration/{uuid.uuid4().hex}.txt"
        try:
            url = await object_storage.upload_bytes(
                object_key=key,
                body=b"integration object",
                content_type="text/plain",
            )
            self.assertTrue(url)
        finally:
            await object_storage.delete_object(key)
