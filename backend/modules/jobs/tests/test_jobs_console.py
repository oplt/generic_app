"""Unit tests for the operational jobs console."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.modules.jobs.service import (
    JobsConsoleService,
    STATUS_CANCELLED,
    _redact_payload_summary,
)
from backend.workers.job_service import STATUS_QUEUED, STATUS_RUNNING


class PayloadRedactionTest(unittest.TestCase):
    def test_redacts_secret_field_names(self) -> None:
        summary = _redact_payload_summary(
            {"field_names": ["document_id", "api_key", "password"], "source": "celery"}
        )
        self.assertEqual(summary["field_names"], ["document_id"])
        self.assertEqual(summary["redacted_field_count"], 2)
        self.assertNotIn("api_key", summary["field_names"])


class JobsConsoleSerializeTest(unittest.TestCase):
    def test_application_queued_is_cancellable(self) -> None:
        service = JobsConsoleService(MagicMock())
        job = SimpleNamespace(
            id="app-1",
            job_type="email",
            status=STATUS_QUEUED,
            created_at=datetime.now(UTC),
            started_at=None,
            finished_at=None,
            available_at=datetime.now(UTC),
            attempts=0,
            max_attempts=3,
            correlation_id="c1",
            operation_id="op-1",
            last_error=None,
            payload={"field_names": ["to", "subject"], "source": "celery"},
        )
        item = service._serialize_application(job, now=datetime.now(UTC))
        self.assertEqual(item["state"], "queued")
        self.assertTrue(item["can_cancel"])
        self.assertFalse(item["can_retry"])

    def test_stale_running_is_detected(self) -> None:
        service = JobsConsoleService(MagicMock())
        now = datetime.now(UTC)
        job = SimpleNamespace(
            id="app-2",
            job_type="outbox-dispatch",
            status=STATUS_RUNNING,
            created_at=now - timedelta(hours=2),
            started_at=now - timedelta(hours=2),
            finished_at=None,
            available_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
            attempts=1,
            max_attempts=3,
            correlation_id="c2",
            operation_id=None,
            last_error=None,
            payload={"field_names": []},
        )
        with patch(
            "backend.workers.job_service.settings.WORKER_JOB_RUNNING_LEASE_SECONDS",
            60,
        ):
            item = service._serialize_application(job, now=now)
        self.assertEqual(item["state"], "stale")
        self.assertTrue(item["stale"])


class JobsConsoleAuthzActionsTest(unittest.IsolatedAsyncioTestCase):
    async def test_retry_rejects_unsupported_application_job(self) -> None:
        db = MagicMock()
        service = JobsConsoleService(db)
        service.get_job = AsyncMock(
            return_value={
                "id": "app-1",
                "source": "application",
                "job_type": "email",
                "can_retry": False,
                "retry_blocked_reason": "Retry from console is only supported for RAG ingestion jobs",
            }
        )
        with self.assertRaises(Exception) as raised:
            await service.retry_job("app-1", actor_id="u1", is_admin=True)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_cancel_queued_application_job(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        job = SimpleNamespace(
            id="app-1",
            status=STATUS_QUEUED,
            finished_at=None,
            last_error=None,
        )
        db.get = AsyncMock(return_value=job)
        service = JobsConsoleService(db)
        service.get_job = AsyncMock(
            side_effect=[
                {
                    "id": "app-1",
                    "source": "application",
                    "can_cancel": True,
                },
                {
                    "id": "app-1",
                    "source": "application",
                    "state": "cancelled",
                    "raw_status": STATUS_CANCELLED,
                },
            ]
        )
        result = await service.cancel_job("app-1", source="application")
        self.assertEqual(job.status, STATUS_CANCELLED)
        self.assertEqual(result["state"], "cancelled")
        db.commit.assert_awaited()


class JobsFilterTest(unittest.TestCase):
    def test_failed_only_includes_stale_and_failed(self) -> None:
        service = JobsConsoleService(MagicMock())
        items = [
            {"state": "succeeded", "raw_status": "succeeded", "job_type": "a", "queue": "default"},
            {"state": "failed", "raw_status": "failed", "job_type": "a", "queue": "default"},
            {"state": "stale", "raw_status": "running", "job_type": "a", "queue": "default"},
        ]
        filtered = service._apply_filters(
            items, status=None, job_type=None, queue=None, failed_only=True
        )
        self.assertEqual([item["state"] for item in filtered], ["failed", "stale"])
