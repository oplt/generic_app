"""HTTP Idempotency-Key and Celery effect-idempotency helpers."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.lib.idempotency import (
    IdempotencyConflictError,
    IdempotencySession,
    celery_operation_key,
    fingerprint_payload,
    run_with_effect_idempotency,
    validate_idempotency_key,
)
from backend.lib.idempotency.models import (
    SCOPE_HTTP,
    STATUS_COMPLETED,
    STATUS_PROCESSING,
    IdempotencyRecord,
)
from backend.lib.idempotency.service import IdempotencyService, cleanup_expired_idempotency_records
from backend.workers.effect_ledger import (
    EFFECT_EMAIL,
    STATUS_SUCCEEDED,
    ExternalEffectInFlightError,
    hash_effect_payload,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _MemorySession:
    def __init__(self, store: dict[str, object]):
        self.store = store
        self._pending: list[object] = []
        self._locked: object | None = None

    async def scalar(self, statement):
        del statement
        for value in self.store.values():
            if isinstance(value, IdempotencyRecord):
                return value
        return None

    def add(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = str(uuid4())
        self._pending.append(obj)

    async def scalars(self, statement):
        del statement
        now = datetime.now(UTC)
        ids = [
            value.id
            for value in self.store.values()
            if isinstance(value, IdempotencyRecord) and value.expires_at <= now
        ]

        class _Result:
            def all(self_inner):
                return ids

        return _Result()

    async def execute(self, statement):
        del statement
        expired = [
            key
            for key, value in list(self.store.items())
            if isinstance(value, IdempotencyRecord)
            and value.expires_at <= datetime.now(UTC)
        ]
        for key in expired:
            self.store.pop(key, None)
        return _ScalarResult(None)

    async def delete(self, obj) -> None:
        self.store.pop(getattr(obj, "id", None), None)

    async def commit(self) -> None:
        for obj in self._pending:
            self.store[obj.id] = obj
        self._pending.clear()

    async def rollback(self) -> None:
        self._pending.clear()


class IdempotencyHelpersTest(unittest.TestCase):
    def test_fingerprint_is_stable(self) -> None:
        first = fingerprint_payload({"b": 1, "a": 2})
        second = fingerprint_payload({"a": 2, "b": 1})
        self.assertEqual(first, second)
        self.assertNotEqual(first, fingerprint_payload({"a": 3, "b": 1}))

    def test_validate_idempotency_key(self) -> None:
        self.assertEqual(validate_idempotency_key("abc-12345"), "abc-12345")
        with self.assertRaises(ValueError):
            validate_idempotency_key("short")

    def test_celery_operation_key(self) -> None:
        self.assertEqual(
            celery_operation_key("webhook", "dispatch", "evt-1"),
            "webhook:dispatch:evt-1",
        )


class IdempotencyServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store: dict[str, object] = {}
        self.db = _MemorySession(self.store)
        self.service = IdempotencyService(self.db)
        self.settings = SimpleNamespace(
            IDEMPOTENCY_TTL_SECONDS=3600,
            IDEMPOTENCY_LEASE_SECONDS=30,
            IDEMPOTENCY_WAIT_SECONDS=0.2,
            IDEMPOTENCY_WAIT_POLL_SECONDS=0.01,
        )

    async def test_process_complete_and_replay(self) -> None:
        with patch("backend.lib.idempotency.service.settings", self.settings):
            first = await self.service.begin_http(
                scope_key="user:u1",
                endpoint="projects.create",
                idempotency_key="key-12345",
                request_fingerprint="fp-a",
            )
            self.assertTrue(first.should_process)
            await self.service.complete(
                record_id=first.record_id,
                response_status_code=201,
                response_body={"id": "proj-1"},
            )
            second = await self.service.begin_http(
                scope_key="user:u1",
                endpoint="projects.create",
                idempotency_key="key-12345",
                request_fingerprint="fp-a",
            )
        self.assertFalse(second.should_process)
        self.assertEqual(second.status, STATUS_COMPLETED)
        self.assertEqual(second.response_body, {"id": "proj-1"})

    async def test_conflict_on_fingerprint_mismatch(self) -> None:
        with patch("backend.lib.idempotency.service.settings", self.settings):
            first = await self.service.begin_http(
                scope_key="user:u1",
                endpoint="projects.create",
                idempotency_key="key-12345",
                request_fingerprint="fp-a",
            )
            await self.service.complete(
                record_id=first.record_id,
                response_status_code=201,
                response_body={"id": "proj-1"},
            )
            with self.assertRaises(IdempotencyConflictError):
                await self.service.begin_http(
                    scope_key="user:u1",
                    endpoint="projects.create",
                    idempotency_key="key-12345",
                    request_fingerprint="fp-b",
                )

    async def test_concurrent_wait_replays_completed_result(self) -> None:
        with patch("backend.lib.idempotency.service.settings", self.settings):
            first = await self.service.begin_http(
                scope_key="user:u1",
                endpoint="projects.create",
                idempotency_key="key-99999",
                request_fingerprint="fp-a",
            )

            async def complete_later() -> None:
                await asyncio.sleep(0.05)
                await self.service.complete(
                    record_id=first.record_id,
                    response_status_code=201,
                    response_body={"id": "proj-2"},
                )

            waiter = asyncio.create_task(
                self.service.begin_http(
                    scope_key="user:u1",
                    endpoint="projects.create",
                    idempotency_key="key-99999",
                    request_fingerprint="fp-a",
                )
            )
            await complete_later()
            second = await waiter

        self.assertFalse(second.should_process)
        self.assertEqual(second.response_body, {"id": "proj-2"})

    async def test_failed_claim_can_be_reclaimed(self) -> None:
        with patch("backend.lib.idempotency.service.settings", self.settings):
            first = await self.service.begin_http(
                scope_key="user:u1",
                endpoint="projects.create",
                idempotency_key="key-fail01",
                request_fingerprint="fp-a",
            )
            await self.service.fail(record_id=first.record_id, error="boom")
            second = await self.service.begin_http(
                scope_key="user:u1",
                endpoint="projects.create",
                idempotency_key="key-fail01",
                request_fingerprint="fp-a",
            )
        self.assertTrue(second.should_process)
        self.assertEqual(second.status, STATUS_PROCESSING)

    async def test_cleanup_deletes_expired_rows(self) -> None:
        now = datetime.now(UTC)
        expired = IdempotencyRecord(
            id=str(uuid4()),
            scope_type=SCOPE_HTTP,
            scope_key="user:u1",
            endpoint="projects.create",
            idempotency_key="key-old-01",
            request_fingerprint="fp",
            status=STATUS_COMPLETED,
            lease_expires_at=now - timedelta(hours=2),
            expires_at=now - timedelta(minutes=1),
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1),
        )
        self.store[expired.id] = expired
        deleted = await cleanup_expired_idempotency_records(self.db)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.store, {})


class IdempotencySessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_execute_replays_cached_response(self) -> None:
        session = IdempotencySession(
            enabled=True,
            should_process=False,
            replay_status_code=201,
            replay_body={"id": "proj-1", "name": "Alpha"},
        )
        producer = AsyncMock(return_value={"should": "not-run"})
        response = await session.execute(producer, status_code=201)
        producer.assert_not_awaited()
        self.assertEqual(response.status_code, 201)
        import json

        self.assertEqual(json.loads(response.body), {"id": "proj-1", "name": "Alpha"})

    async def test_execute_completes_on_success(self) -> None:
        service = MagicMock()
        service.complete = AsyncMock()
        service.fail = AsyncMock()
        session = IdempotencySession(
            enabled=True,
            service=service,
            claim_record_id="rec-1",
            should_process=True,
        )
        result = await session.execute(
            AsyncMock(return_value=SimpleNamespace(id="p1")),
            status_code=201,
            dump=lambda value: {"id": value.id},
        )
        self.assertEqual(result.id, "p1")
        service.complete.assert_awaited_once()
        service.fail.assert_not_awaited()


class CeleryEffectHelperTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_with_effect_idempotency_skips_duplicate_success(self) -> None:
        execute = AsyncMock(return_value="sent")
        claim = SimpleNamespace(
            should_execute=False,
            status=STATUS_SUCCEEDED,
            provider_idempotency_key="msg-1",
            effect_id="e1",
            attempts=1,
        )
        with patch(
            "backend.lib.idempotency.celery_ops.begin_external_effect",
            AsyncMock(return_value=claim),
        ):
            result = await run_with_effect_idempotency(
                operation_id="email:1",
                effect_type=EFFECT_EMAIL,
                payload_parts=("a@example.com", "Hi", "<p>Hi</p>", "Hi"),
                execute=execute,
            )
        self.assertIsNone(result)
        execute.assert_not_awaited()

    async def test_run_with_effect_idempotency_raises_when_in_flight(self) -> None:
        claim = SimpleNamespace(
            should_execute=False,
            status="in_flight",
            provider_idempotency_key="msg-1",
            effect_id="e1",
            attempts=1,
        )
        with (
            patch(
                "backend.lib.idempotency.celery_ops.begin_external_effect",
                AsyncMock(return_value=claim),
            ),
            self.assertRaises(ExternalEffectInFlightError),
        ):
            await run_with_effect_idempotency(
                operation_id="email:2",
                effect_type=EFFECT_EMAIL,
                payload_parts=("a@example.com", "Hi", "<p>Hi</p>", None),
                execute=AsyncMock(),
            )

    async def test_run_with_effect_idempotency_executes_once(self) -> None:
        claim = SimpleNamespace(
            should_execute=True,
            status="in_flight",
            provider_idempotency_key="msg-9",
            effect_id="e9",
            attempts=1,
        )
        execute = AsyncMock(return_value="ok")
        complete = AsyncMock()
        with (
            patch(
                "backend.lib.idempotency.celery_ops.begin_external_effect",
                AsyncMock(return_value=claim),
            ),
            patch(
                "backend.lib.idempotency.celery_ops.complete_external_effect",
                complete,
            ),
        ):
            result = await run_with_effect_idempotency(
                operation_id="email:3",
                effect_type=EFFECT_EMAIL,
                payload_parts=("a@example.com", "Hi", "<p>Hi</p>", None),
                execute=execute,
            )
        self.assertEqual(result, "ok")
        execute.assert_awaited_once_with("msg-9")
        complete.assert_awaited()
        self.assertEqual(
            hash_effect_payload("a@example.com", "Hi", "<p>Hi</p>", None),
            hash_effect_payload("a@example.com", "Hi", "<p>Hi</p>", None),
        )
