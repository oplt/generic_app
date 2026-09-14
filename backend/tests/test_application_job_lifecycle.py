"""Logical ApplicationJob lifecycle across retries and queue latency."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from backend.workers.async_dispatch import run_async_in_sync_context
from backend.workers.job_service import (
    STATUS_DEAD_LETTER,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    ensure_queued_job,
    run_tracked_sync,
)
from backend.workers.models import ApplicationJob


class _MemorySession:
    def __init__(self, store: dict[str, object]):
        self.store = store
        self._pending: list[object] = []

    async def scalar(self, statement):
        del statement
        for value in self.store.values():
            if isinstance(value, ApplicationJob):
                return value
        return None

    def add(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = str(uuid4())
        self._pending.append(obj)

    async def get(self, model, key):
        del model
        return self.store.get(key)

    async def commit(self) -> None:
        for obj in self._pending:
            self.store[obj.id] = obj
        self._pending.clear()

    async def rollback(self) -> None:
        self._pending.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _SessionFactory:
    def __init__(self, store: dict[str, object]):
        self.store = store

    def __call__(self):
        return _MemorySession(self.store)


def _jobs(store: dict[str, object]) -> list[ApplicationJob]:
    return [value for value in store.values() if isinstance(value, ApplicationJob)]


class ApplicationJobLifecycleTest(unittest.TestCase):
    def test_success_after_retry_keeps_one_logical_job(self):
        store: dict[str, object] = {}
        operation_id = f"job:{uuid4().hex}"
        calls = {"n": 0}

        def runner():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")

        with patch("backend.workers.job_service.SessionLocal", _SessionFactory(store)):
            with self.assertRaises(RuntimeError):
                run_tracked_sync(
                    job_type="demo",
                    payload={"x": 1},
                    runner=runner,
                    operation_id=operation_id,
                    correlation_id=operation_id,
                    max_attempts=3,
                )
            run_tracked_sync(
                job_type="demo",
                payload={"x": 1},
                runner=runner,
                operation_id=operation_id,
                correlation_id=operation_id,
                max_attempts=3,
            )

        jobs = _jobs(store)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, STATUS_SUCCEEDED)
        self.assertEqual(jobs[0].attempts, 2)
        self.assertEqual(calls["n"], 2)

    def test_max_attempts_marks_dead_letter(self):
        store: dict[str, object] = {}
        operation_id = f"job:{uuid4().hex}"

        def runner():
            raise TimeoutError("soft time limit")

        with patch("backend.workers.job_service.SessionLocal", _SessionFactory(store)):
            for _ in range(2):
                with self.assertRaises(TimeoutError):
                    run_tracked_sync(
                        job_type="demo",
                        payload={},
                        runner=runner,
                        operation_id=operation_id,
                        correlation_id=operation_id,
                        max_attempts=2,
                    )
            # Third claim exhausts attempts before running.
            run_tracked_sync(
                job_type="demo",
                payload={},
                runner=runner,
                operation_id=operation_id,
                correlation_id=operation_id,
                max_attempts=2,
            )

        jobs = _jobs(store)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, STATUS_DEAD_LETTER)
        self.assertGreaterEqual(jobs[0].attempts, 2)

    def test_worker_lost_stale_running_is_reclaimed(self):
        store: dict[str, object] = {}
        operation_id = f"job:{uuid4().hex}"
        stale = ApplicationJob(
            id=str(uuid4()),
            job_type="demo",
            status=STATUS_RUNNING,
            correlation_id=operation_id,
            operation_id=operation_id,
            payload={"field_names": [], "source": "celery"},
            attempts=1,
            max_attempts=3,
            retryable=True,
            available_at=datetime.now(UTC) - timedelta(minutes=30),
            started_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        store[stale.id] = stale
        ran = {"ok": False}

        with (
            patch("backend.workers.job_service.SessionLocal", _SessionFactory(store)),
            patch(
                "backend.workers.job_service.settings",
                SimpleNamespace(
                    WORKER_JOB_RUNNING_LEASE_SECONDS=60,
                    WORKER_JOB_DEFAULT_MAX_ATTEMPTS=3,
                    EXTERNAL_EFFECT_LEASE_SECONDS=600,
                ),
            ),
        ):
            run_tracked_sync(
                job_type="demo",
                payload={},
                runner=lambda: ran.__setitem__("ok", True),
                operation_id=operation_id,
                correlation_id=operation_id,
                max_attempts=3,
            )

        self.assertTrue(ran["ok"])
        self.assertEqual(stale.status, STATUS_SUCCEEDED)
        self.assertEqual(stale.attempts, 2)

    def test_queue_latency_measured_from_available_at(self):
        store: dict[str, object] = {}
        operation_id = f"job:{uuid4().hex}"
        queue_observed: list[float] = []

        class _QueueLatency:
            def labels(self, *_args, **_kwargs):
                return self

            def observe(self, value):
                queue_observed.append(value)

        class _NoopMetric:
            def labels(self, *_args, **_kwargs):
                return self

            def observe(self, value):
                del value

            def inc(self):
                return None

        with (
            patch("backend.workers.job_service.SessionLocal", _SessionFactory(store)),
            patch(
                "backend.workers.job_service.worker_job_queue_latency_seconds",
                _QueueLatency(),
            ),
            patch("backend.workers.job_service.worker_jobs_total", _NoopMetric()),
            patch("backend.workers.job_service.worker_job_duration_seconds", _NoopMetric()),
            patch("backend.workers.job_service.worker_job_retries_total", _NoopMetric()),
        ):
            run_async_in_sync_context(
                ensure_queued_job(
                    job_type="demo",
                    payload={"a": 1},
                    correlation_id=operation_id,
                    operation_id=operation_id,
                    max_attempts=3,
                )
            )
            job = _jobs(store)[0]
            job.available_at = datetime.now(UTC) - timedelta(seconds=12)
            run_tracked_sync(
                job_type="demo",
                payload={"a": 1},
                runner=lambda: None,
                operation_id=operation_id,
                correlation_id=operation_id,
                max_attempts=3,
            )

        self.assertEqual(len(queue_observed), 1)
        self.assertGreaterEqual(queue_observed[0], 11.0)
        self.assertEqual(_jobs(store)[0].status, STATUS_SUCCEEDED)

    def test_duplicate_success_is_deduplicated(self):
        store: dict[str, object] = {}
        operation_id = f"job:{uuid4().hex}"
        runs: list[str] = []

        with patch("backend.workers.job_service.SessionLocal", _SessionFactory(store)):
            run_tracked_sync(
                job_type="email",
                payload={"to": "user@example.com"},
                runner=lambda: runs.append("run"),
                operation_id=operation_id,
                correlation_id=operation_id,
            )
            run_tracked_sync(
                job_type="email",
                payload={"to": "user@example.com"},
                runner=lambda: runs.append("run"),
                operation_id=operation_id,
                correlation_id=operation_id,
            )

        self.assertEqual(runs, ["run"])
        self.assertEqual(_jobs(store)[0].status, STATUS_SUCCEEDED)

    def test_deadline_exceeded_marks_dead_letter_without_running(self):
        store: dict[str, object] = {}
        operation_id = f"job:{uuid4().hex}"
        job = ApplicationJob(
            id=str(uuid4()),
            job_type="demo",
            status=STATUS_QUEUED,
            correlation_id=operation_id,
            operation_id=operation_id,
            payload={"field_names": [], "source": "celery"},
            attempts=0,
            max_attempts=3,
            retryable=True,
            available_at=datetime.now(UTC) - timedelta(hours=1),
            deadline_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        store[job.id] = job
        ran = False

        def runner():
            nonlocal ran
            ran = True

        with patch("backend.workers.job_service.SessionLocal", _SessionFactory(store)):
            run_tracked_sync(
                job_type="demo",
                payload={},
                runner=runner,
                operation_id=operation_id,
                correlation_id=operation_id,
            )

        self.assertFalse(ran)
        self.assertEqual(job.status, STATUS_DEAD_LETTER)
        self.assertEqual(job.last_error, "deadline_exceeded")


if __name__ == "__main__":
    unittest.main()
