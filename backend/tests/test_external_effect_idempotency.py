"""Idempotent email effect ledger and duplicate Celery delivery coverage."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.workers.effect_ledger import (
    EFFECT_EMAIL,
    STATUS_FAILED,
    STATUS_IN_FLIGHT,
    STATUS_SUCCEEDED,
    ExternalEffectInFlightError,
    begin_external_effect,
    complete_external_effect,
    hash_effect_payload,
)
from backend.workers.email import send_email
from backend.workers.job_service import run_tracked_sync
from backend.workers.models import ApplicationJob, ExternalEffect


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _MemorySession:
    def __init__(self, store: dict[str, object]):
        self.store = store
        self._pending: list[object] = []

    async def scalar(self, statement):
        del statement
        # Tests only look up by the single operation under exercise.
        for value in self.store.values():
            if isinstance(value, ExternalEffect):
                return value
            if isinstance(value, ApplicationJob):
                return value
        return None

    def add(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = str(uuid4())
        self._pending.append(obj)

    async def get(self, model, key):
        del model
        value = self.store.get(key)
        return value

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


class CountingSMTP:
    def __init__(self):
        self.calls: list[str] = []
        self.message_ids: list[str] = []

    async def send(self, message, **kwargs):
        del kwargs
        message_id = message["Message-ID"]
        self.calls.append(message_id)
        if message_id not in self.message_ids:
            self.message_ids.append(message_id)


class ExternalEffectLedgerTest(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_claim_after_success_skips(self):
        store: dict[str, object] = {}
        payload_hash = hash_effect_payload("a@example.com", "Hello", "<p>Hi</p>", "Hi")
        with patch("backend.workers.effect_ledger.SessionLocal", _SessionFactory(store)):
            first = await begin_external_effect(
                operation_id="op-1",
                effect_type=EFFECT_EMAIL,
                payload_hash=payload_hash,
            )
            await complete_external_effect(
                operation_id="op-1",
                effect_type=EFFECT_EMAIL,
                status=STATUS_SUCCEEDED,
            )
            second = await begin_external_effect(
                operation_id="op-1",
                effect_type=EFFECT_EMAIL,
                payload_hash=payload_hash,
            )

        self.assertTrue(first.should_execute)
        self.assertFalse(second.should_execute)
        self.assertEqual(second.status, STATUS_SUCCEEDED)

    async def test_fresh_in_flight_claim_is_deferred(self):
        store: dict[str, object] = {}
        payload_hash = hash_effect_payload("a@example.com", "Hello", "<p>Hi</p>", None)
        with patch("backend.workers.effect_ledger.SessionLocal", _SessionFactory(store)):
            first = await begin_external_effect(
                operation_id="op-2",
                effect_type=EFFECT_EMAIL,
                payload_hash=payload_hash,
            )
            second = await begin_external_effect(
                operation_id="op-2",
                effect_type=EFFECT_EMAIL,
                payload_hash=payload_hash,
            )

        self.assertTrue(first.should_execute)
        self.assertFalse(second.should_execute)
        self.assertEqual(second.status, STATUS_IN_FLIGHT)

    async def test_stale_in_flight_and_failed_claims_are_reclaimed(self):
        store: dict[str, object] = {}
        payload_hash = hash_effect_payload("a@example.com", "Hello", "<p>Hi</p>", None)
        with (
            patch("backend.workers.effect_ledger.SessionLocal", _SessionFactory(store)),
            patch("backend.workers.effect_ledger.settings") as mock_settings,
        ):
            mock_settings.EXTERNAL_EFFECT_LEASE_SECONDS = 1
            first = await begin_external_effect(
                operation_id="op-3",
                effect_type=EFFECT_EMAIL,
                payload_hash=payload_hash,
            )
            effect = next(value for value in store.values() if isinstance(value, ExternalEffect))
            effect.started_at = datetime.now(UTC) - timedelta(seconds=5)
            reclaimed = await begin_external_effect(
                operation_id="op-3",
                effect_type=EFFECT_EMAIL,
                payload_hash=payload_hash,
            )
            await complete_external_effect(
                operation_id="op-3",
                effect_type=EFFECT_EMAIL,
                status=STATUS_FAILED,
                error="smtp down",
            )
            after_failure = await begin_external_effect(
                operation_id="op-3",
                effect_type=EFFECT_EMAIL,
                payload_hash=payload_hash,
            )

        self.assertTrue(first.should_execute)
        self.assertTrue(reclaimed.should_execute)
        self.assertEqual(reclaimed.attempts, 2)
        self.assertTrue(after_failure.should_execute)
        self.assertEqual(after_failure.attempts, 3)


class EmailEffectIdempotencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store: dict[str, object] = {}
        self.smtp = CountingSMTP()
        self.settings = SimpleNamespace(
            SMTP_HOST="localhost",
            SMTP_PORT=1025,
            SMTP_FROM="noreply@example.com",
            SMTP_USER="",
            SMTP_PASSWORD="",
            SMTP_TLS=False,
            EXTERNAL_EFFECT_LEASE_SECONDS=600,
        )

    async def test_duplicate_delivery_after_success_sends_once(self):
        operation_id = f"email:{uuid4().hex}"
        with (
            patch("backend.workers.effect_ledger.SessionLocal", _SessionFactory(self.store)),
            patch("backend.workers.email.settings", self.settings),
            patch.dict("sys.modules", {"aiosmtplib": SimpleNamespace(send=self.smtp.send)}),
        ):
            await send_email(
                to="user@example.com",
                subject="Welcome",
                html_body="<p>Hi</p>",
                text_body="Hi",
                operation_id=operation_id,
            )
            await send_email(
                to="user@example.com",
                subject="Welcome",
                html_body="<p>Hi</p>",
                text_body="Hi",
                operation_id=operation_id,
            )

        self.assertEqual(len(self.smtp.calls), 1)
        self.assertEqual(len(self.smtp.message_ids), 1)
        effect = next(value for value in self.store.values() if isinstance(value, ExternalEffect))
        self.assertEqual(effect.status, STATUS_SUCCEEDED)

    async def test_kill_before_provider_acceptance_retries_to_one_send(self):
        operation_id = f"email:{uuid4().hex}"
        deliver = AsyncMock(side_effect=[RuntimeError("worker killed before smtp"), None])

        with (
            patch("backend.workers.effect_ledger.SessionLocal", _SessionFactory(self.store)),
            patch("backend.workers.email.settings", self.settings),
            patch("backend.workers.email._deliver_email", deliver),
        ):
            with self.assertRaises(RuntimeError):
                await send_email(
                    to="user@example.com",
                    subject="Welcome",
                    html_body="<p>Hi</p>",
                    operation_id=operation_id,
                )
            effect = next(
                value for value in self.store.values() if isinstance(value, ExternalEffect)
            )
            self.assertEqual(effect.status, STATUS_FAILED)

            await send_email(
                to="user@example.com",
                subject="Welcome",
                html_body="<p>Hi</p>",
                operation_id=operation_id,
            )

        self.assertEqual(deliver.await_count, 2)
        effect = next(value for value in self.store.values() if isinstance(value, ExternalEffect))
        self.assertEqual(effect.status, STATUS_SUCCEEDED)

    async def test_kill_after_provider_acceptance_keeps_one_visible_effect(self):
        operation_id = f"email:{uuid4().hex}"
        calls = {"count": 0}

        async def deliver_once_then_succeed(**kwargs):
            calls["count"] += 1
            await self.smtp.send({"Message-ID": kwargs["message_id"]})
            if calls["count"] == 1:
                raise SystemExit("worker killed after smtp accept")

        with (
            patch("backend.workers.effect_ledger.SessionLocal", _SessionFactory(self.store)),
            patch("backend.workers.email.settings", self.settings),
            patch("backend.workers.email._deliver_email", side_effect=deliver_once_then_succeed),
        ):
            with self.assertRaises(SystemExit):
                await send_email(
                    to="user@example.com",
                    subject="Welcome",
                    html_body="<p>Hi</p>",
                    operation_id=operation_id,
                )

            effect = next(
                value for value in self.store.values() if isinstance(value, ExternalEffect)
            )
            self.assertEqual(effect.status, STATUS_IN_FLIGHT)

            with (
                patch("backend.workers.effect_ledger.settings") as ledger_settings,
                self.assertRaises(ExternalEffectInFlightError),
            ):
                ledger_settings.EXTERNAL_EFFECT_LEASE_SECONDS = 600
                await send_email(
                    to="user@example.com",
                    subject="Welcome",
                    html_body="<p>Hi</p>",
                    operation_id=operation_id,
                )

            effect.started_at = datetime.now(UTC) - timedelta(seconds=900)
            with patch("backend.workers.effect_ledger.settings") as ledger_settings:
                ledger_settings.EXTERNAL_EFFECT_LEASE_SECONDS = 600
                await send_email(
                    to="user@example.com",
                    subject="Welcome",
                    html_body="<p>Hi</p>",
                    operation_id=operation_id,
                )

        self.assertEqual(len(self.smtp.calls), 2)
        self.assertEqual(len(self.smtp.message_ids), 1)
        effect = next(value for value in self.store.values() if isinstance(value, ExternalEffect))
        self.assertEqual(effect.status, STATUS_SUCCEEDED)


class TrackedEmailJobHistoryTest(unittest.TestCase):
    def test_duplicate_operation_reuses_one_job_history(self):
        store: dict[str, object] = {}
        operation_id = f"email:{uuid4().hex}"
        runs: list[str] = []

        def runner():
            runs.append("run")

        with patch("backend.workers.job_service.SessionLocal", _SessionFactory(store)):
            run_tracked_sync(
                job_type="email",
                payload={"to": "user@example.com"},
                runner=runner,
                operation_id=operation_id,
                correlation_id=operation_id,
            )
            run_tracked_sync(
                job_type="email",
                payload={"to": "user@example.com"},
                runner=runner,
                operation_id=operation_id,
                correlation_id=operation_id,
            )

        jobs = [value for value in store.values() if isinstance(value, ApplicationJob)]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].operation_id, operation_id)
        self.assertEqual(jobs[0].status, "succeeded")
        self.assertEqual(runs, ["run"])
