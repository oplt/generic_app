"""Tests for shared async concurrency helpers."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from backend.lib.concurrency import (
    LoopLocalLimiter,
    RetryNotAllowedError,
    backoff_delay,
    bounded_gather,
    map_concurrently,
    retry_async,
    run_with_timeout,
)


class BackoffDelayTest(unittest.TestCase):
    def test_respects_retry_after_seconds(self) -> None:
        delay = backoff_delay(0, retry_after="2.5", max_delay_seconds=10)
        self.assertEqual(delay, 2.5)

    def test_exponential_grows_with_attempt(self) -> None:
        with patch("backend.lib.concurrency.random.uniform", return_value=0.0):
            first = backoff_delay(0, base_delay_seconds=1.0, jitter_seconds=0.0)
            second = backoff_delay(1, base_delay_seconds=1.0, jitter_seconds=0.0)
            third = backoff_delay(2, base_delay_seconds=1.0, jitter_seconds=0.0)
        self.assertEqual(first, 1.0)
        self.assertEqual(second, 2.0)
        self.assertEqual(third, 4.0)


class BoundedConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_map_concurrently_respects_limit(self) -> None:
        in_flight = 0
        peak = 0

        async def worker(_item: int) -> int:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return _item

        results = await map_concurrently(
            list(range(8)),
            worker,
            limit=3,
            kind="test_map",
        )
        self.assertEqual(results, list(range(8)))
        self.assertLessEqual(peak, 3)

    async def test_bounded_gather_limits_concurrency(self) -> None:
        in_flight = 0
        peak = 0

        async def work(value: int) -> int:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return value

        results = await bounded_gather(
            [work(i) for i in range(6)],
            limit=2,
            kind="test_gather",
        )
        self.assertEqual(results, list(range(6)))
        self.assertLessEqual(peak, 2)

    async def test_run_with_timeout_cancels(self) -> None:
        async def slow() -> str:
            await asyncio.sleep(1.0)
            return "done"

        with self.assertRaises(TimeoutError):
            await run_with_timeout(slow(), timeout_seconds=0.05, kind="test_timeout")

    async def test_retry_async_retries_then_succeeds(self) -> None:
        calls = 0

        async def flaky() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("transient")
            return "ok"

        with (
            patch("backend.lib.concurrency.asyncio.sleep", asyncio.sleep),
            patch("backend.lib.concurrency.backoff_delay", return_value=0.0),
        ):
            value = await retry_async(
                flaky,
                max_attempts=3,
                kind="test_retry",
            )
        self.assertEqual(value, "ok")
        self.assertEqual(calls, 3)

    async def test_retry_async_skips_non_retryable(self) -> None:
        calls = 0

        async def boom() -> None:
            nonlocal calls
            calls += 1
            raise ValueError("bad input")

        with self.assertRaises(ValueError):
            await retry_async(
                boom,
                max_attempts=5,
                retryable_exceptions=(RuntimeError,),
                non_retryable_exceptions=(ValueError,),
                kind="test_non_retryable",
            )
        self.assertEqual(calls, 1)

    async def test_retry_async_refuses_non_idempotent(self) -> None:
        with self.assertRaises(RetryNotAllowedError):
            await retry_async(
                lambda: asyncio.sleep(0),
                max_attempts=3,
                idempotent=False,
                kind="test_non_idempotent",
            )

    async def test_loop_local_limiter_slot_timeout(self) -> None:
        limiter = LoopLocalLimiter("test_slot")
        async with limiter.slot(1, kind="test_slot"):
            with self.assertRaises(TimeoutError):
                async with limiter.slot(1, timeout_seconds=0.05, kind="test_slot"):
                    pass

    async def test_cancellation_propagates_from_map(self) -> None:
        started = asyncio.Event()

        async def worker(_item: int) -> int:
            started.set()
            await asyncio.sleep(10)
            return _item

        task = asyncio.create_task(
            map_concurrently([1], worker, limit=1, kind="test_cancel")
        )
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
