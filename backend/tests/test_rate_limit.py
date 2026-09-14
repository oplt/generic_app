import unittest
from unittest.mock import AsyncMock, patch

from redis.exceptions import ConnectionError

from backend.core.rate_limit import check_rate_limit, increment_rate_limit


class RateLimitTest(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_uses_one_atomic_redis_script_call(self) -> None:
        with patch("backend.core.rate_limit.redis_client") as client:
            client.eval = AsyncMock(return_value=2)
            client.ttl = AsyncMock(return_value=10)

            await increment_rate_limit("rate:test", 60)

            client.eval.assert_awaited_once()
            client.incr.assert_not_called()
            client.expire.assert_not_called()

    async def test_rate_limit_has_bounded_local_fallback_when_redis_is_down(self) -> None:
        with patch("backend.core.rate_limit.redis_client") as client:
            client.eval = AsyncMock(side_effect=ConnectionError())
            await check_rate_limit("rate:fallback", 2, 60)
            await check_rate_limit("rate:fallback", 2, 60)

            with self.assertRaises(Exception) as context:
                await check_rate_limit("rate:fallback", 2, 60)

        self.assertEqual(getattr(context.exception, "status_code", None), 429)
