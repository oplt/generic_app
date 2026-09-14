import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from celery.exceptions import Retry

from backend.modules.rag.application.document_ingestion_service import (
    DocumentIngestionService,
    IngestionJobBusyError,
)
from backend.workers.outbox import OutboxClaim, _ack_claim, dispatch_pending_job_events
from backend.workers.tasks import enqueue_outbox_job, index_rag_document_task


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, row, *, ack_rowcount=1):
        self.events = []
        self._row = row
        self._execute_count = 0
        self._ack_rowcount = ack_rowcount

    async def execute(self, statement):
        self.events.append(("execute", statement))
        self._execute_count += 1
        if self._execute_count == 1:
            return _Result([self._row])
        return _Result(rowcount=self._ack_rowcount)

    async def flush(self):
        self.events.append(("flush", None))

    async def commit(self):
        self.events.append(("commit", None))

    async def rollback(self):
        self.events.append(("rollback", None))


def _outbox_row():
    return SimpleNamespace(
        id="outbox-1",
        job_id="job-1",
        job_type="rag-indexing",
        payload={"document_id": "doc-1", "user_id": "user-1", "job_id": "job-1"},
        status="pending",
        attempts=0,
        available_at=datetime.now(UTC) - timedelta(seconds=1),
        deadline_at=None,
        locked_at=None,
        lease_token=None,
        dispatched_at=None,
        last_error=None,
    )


class OutboxDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_claim_commits_before_broker_publish_and_ack(self):
        row = _outbox_row()
        db = _Session(row)
        publisher = MagicMock()

        def publish(**kwargs):
            db.events.append(("publish", kwargs))

        publisher.apply_async.side_effect = publish
        with patch("backend.workers.tasks.enqueue_outbox_job", publisher):
            dispatched = await dispatch_pending_job_events(db)

        self.assertEqual(dispatched, 1)
        event_names = [name for name, _ in db.events]
        self.assertLess(event_names.index("commit"), event_names.index("publish"))
        self.assertLess(event_names.index("publish"), event_names.index("execute", 1))
        publisher.apply_async.assert_called_once_with(
            kwargs={
                "job_type": "rag-indexing",
                "document_id": "doc-1",
                "user_id": "user-1",
                "job_id": "job-1",
            },
            queue="default",
        )
        self.assertTrue(row.lease_token)

    async def test_publish_failure_releases_claim_for_retry(self):
        row = _outbox_row()
        db = _Session(row)
        publisher = MagicMock()
        publisher.apply_async.side_effect = RuntimeError("broker unavailable")

        with patch("backend.workers.tasks.enqueue_outbox_job", publisher):
            dispatched = await dispatch_pending_job_events(db)

        self.assertEqual(dispatched, 0)
        self.assertEqual([name for name, _ in db.events].count("commit"), 2)
        self.assertEqual([name for name, _ in db.events].count("execute"), 2)

    async def test_ack_compare_and_set_ignores_stale_lease(self):
        db = _Session(_outbox_row(), ack_rowcount=0)
        db._execute_count = 1
        claim = OutboxClaim(
            outbox_id="outbox-1",
            job_id="job-1",
            job_type="rag-indexing",
            payload={"job_id": "job-1"},
            attempts=1,
            lease_token="stale-token",
        )

        result = await _ack_claim(
            db,
            claim,
            dispatched=True,
            now=datetime.now(UTC),
        )

        self.assertFalse(result)
        self.assertEqual([name for name, _ in db.events].count("commit"), 1)

    def test_outbox_consumer_receives_stable_job_operation_key(self):
        with patch("backend.workers.tasks.index_rag_document_task") as task:
            enqueue_outbox_job(
                job_type="rag-indexing",
                document_id="doc-1",
                user_id="user-1",
                job_id="job-1",
            )

        task.apply_async.assert_called_once_with(
            kwargs={
                "document_id": "doc-1",
                "user_id": "user-1",
                "job_id": "job-1",
            }
        )

    def test_busy_consumer_retries_after_the_lease(self):
        with (
            patch(
                "backend.workers.tasks.run_tracked_sync",
                side_effect=IngestionJobBusyError("active"),
            ),
            patch.object(index_rag_document_task, "retry", side_effect=Retry("retry")) as retry,
            self.assertRaises(Retry),
        ):
            index_rag_document_task.run(
                document_id="doc-1",
                user_id="user-1",
                job_id="job-1",
            )

        retry.assert_called_once()
        self.assertEqual(retry.call_args.kwargs["countdown"], 600)

    async def test_duplicate_active_consumer_is_deferred(self):
        service = object.__new__(DocumentIngestionService)
        document = SimpleNamespace(id="doc-1", user_id="user-1")
        job = SimpleNamespace(
            id="job-1",
            document_id="doc-1",
            status="running",
            heartbeat_at=datetime.now(UTC),
        )
        service._get_document_for_indexing = AsyncMock(return_value=document)
        service.repo = MagicMock()
        service.repo.get_ingestion_job = AsyncMock(return_value=job)
        service.parser = MagicMock()

        with self.assertRaises(IngestionJobBusyError):
            await service.index_document(
                document_id="doc-1",
                user_id="user-1",
                job_id="job-1",
            )
        service.parser.parse_bytes.assert_not_called()
