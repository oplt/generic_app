import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.cache import (
    PLATFORM_CONFIG_CACHE_KEY,
    PLATFORM_FEATURE_FLAGS_CACHE_KEY,
    cache_get_json,
    cache_get_many_json,
    cache_get_or_load_json,
    cache_set_json,
    cache_set_many_json,
    embedding_cache_key,
    invalidate_platform_caches,
)


class CacheHelpersTest(unittest.IsolatedAsyncioTestCase):
    async def test_cache_loader_singleflight_runs_loader_once(self):
        state: dict[str, object] = {}
        loader_calls = 0

        async def get_cached(_key):
            return state.get(_key)

        async def set_cached(_key, value, *, ttl_seconds):
            state[_key] = value

        async def loader():
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.01)
            return {"loaded": True}

        with (
            patch("backend.core.cache.cache_get_json", get_cached),
            patch("backend.core.cache.cache_set_json", set_cached),
            patch("backend.core.cache._uses_redis_cache", return_value=False),
        ):
            values = await asyncio.gather(
                cache_get_or_load_json("ga:single-flight", ttl_seconds=30, loader=loader),
                cache_get_or_load_json("ga:single-flight", ttl_seconds=30, loader=loader),
            )

        self.assertEqual(loader_calls, 1)
        self.assertEqual(values, [{"loaded": True}, {"loaded": True}])

    async def test_cache_loader_uses_distributed_lock_when_redis_enabled(self):
        client = AsyncMock()
        client.set = AsyncMock(return_value=True)
        client.eval = AsyncMock(return_value=1)
        with (
            patch("backend.core.cache.cache_get_json", AsyncMock(return_value=None)),
            patch("backend.core.cache.cache_set_json", AsyncMock()),
            patch("backend.core.cache._uses_redis_cache", return_value=True),
            patch("backend.core.cache.redis_client", client),
        ):
            value = await cache_get_or_load_json(
                "ga:distributed-lock",
                ttl_seconds=30,
                loader=AsyncMock(return_value={"loaded": True}),
            )

        self.assertEqual(value, {"loaded": True})
        client.set.assert_awaited_once()
        client.eval.assert_awaited_once()
    async def test_cache_get_returns_none_when_disabled(self):
        with patch("backend.core.cache.settings") as mock_settings:
            mock_settings.CACHE_ENABLED = False
            value = await cache_get_json("ga:test")
        self.assertIsNone(value)

    async def test_cache_set_skips_when_disabled(self):
        client = AsyncMock()
        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", client),
        ):
            mock_settings.CACHE_ENABLED = False
            await cache_set_json("ga:test", {"ok": True}, ttl_seconds=60)
        client.setex.assert_not_called()

    async def test_cache_round_trip_json(self):
        client = AsyncMock()
        client.get = AsyncMock(return_value=None)
        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", client),
        ):
            mock_settings.CACHE_ENABLED = True
            mock_settings.CACHE_MAX_PAYLOAD_BYTES = 1024 * 1024
            await cache_set_json("ga:test", {"count": 2}, ttl_seconds=30)
            client.setex.assert_awaited_once()

            client.get = AsyncMock(return_value='{"count": 2}')
            value = await cache_get_json("ga:test")
        self.assertEqual(value, {"count": 2})

    async def test_cache_batch_round_trip_uses_mget_and_pipeline(self):
        client = AsyncMock()
        client.mget = AsyncMock(return_value=['{"count": 2}', None])
        pipeline = MagicMock()
        pipeline.execute = AsyncMock()
        client.pipeline = MagicMock(return_value=pipeline)
        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", client),
        ):
            mock_settings.CACHE_ENABLED = True
            mock_settings.CACHE_MAX_PAYLOAD_BYTES = 1024 * 1024
            values = await cache_get_many_json(["ga:one", "ga:two"])
            await cache_set_many_json([("ga:one", {"count": 2}, 30), ("ga:two", {"count": 3}, 30)])

        self.assertEqual(values, {"ga:one": {"count": 2}})
        client.mget.assert_awaited_once_with(["ga:one", "ga:two"])
        pipeline.execute.assert_awaited_once()

    def test_embedding_cache_key_is_stable_and_namespaced(self):
        first = embedding_cache_key(
            "openai", "text-embedding-3-small", "hello world", dimensions=1536
        )
        second = embedding_cache_key(
            "openai", "text-embedding-3-small", "hello world", dimensions=1536
        )
        third = embedding_cache_key("openai", "text-embedding-3-small", "other", dimensions=1536)
        different_dims = embedding_cache_key(
            "openai", "text-embedding-3-small", "hello world", dimensions=768
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertNotEqual(first, different_dims)
        self.assertTrue(first.startswith("ga:embed:"))

    async def test_invalidate_platform_caches_deletes_known_keys(self):
        client = AsyncMock()
        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", client),
        ):
            mock_settings.CACHE_ENABLED = True
            await invalidate_platform_caches()

        client.delete.assert_awaited_once_with(
            PLATFORM_CONFIG_CACHE_KEY,
            PLATFORM_FEATURE_FLAGS_CACHE_KEY,
        )

    async def test_cache_delete_pattern_deletes_in_batches(self):
        from backend.core.cache import cache_delete_pattern

        class FakeScanIter:
            def __init__(self, keys):
                self._keys = iter(keys)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._keys)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        client = AsyncMock()
        client.scan_iter = lambda **kwargs: FakeScanIter(
            [f"ga:projects:list:user-1:{index}" for index in range(5)]
        )
        client.delete = AsyncMock()

        with (
            patch("backend.core.cache.settings") as mock_settings,
            patch("backend.core.cache.redis_client", client),
        ):
            mock_settings.CACHE_ENABLED = True
            await cache_delete_pattern("ga:projects:list:user-1:*", batch_size=2)

        self.assertEqual(client.delete.await_count, 3)


class EmbeddingCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_embed_texts_uses_cache_for_repeat_query(self):
        from backend.modules.rag.application.embedding_service import EmbeddingService

        service = EmbeddingService()
        service._adapter = AsyncMock()
        service._adapter.embed_texts = AsyncMock(return_value=[[0.1, 0.2]])
        service_cache_key = embedding_cache_key(
            service.config.embedding_provider,
            service.config.embedding_model,
            "hello",
            dimensions=service.config.embedding_dimensions,
        )

        with (
            patch("backend.lib.embedding_cache.settings") as mock_settings,
            patch(
                "backend.lib.embedding_cache.app_cache.get_many",
                AsyncMock(
                    side_effect=[
                        {},
                        {service_cache_key: [0.1, 0.2]},
                    ]
                ),
            ) as cache_get,
            patch(
                "backend.lib.embedding_cache.app_cache.set_many",
                AsyncMock(),
            ) as cache_set,
        ):
            mock_settings.CACHE_ENABLED = True
            mock_settings.CACHE_EMBEDDING_TTL_SECONDS = 600
            mock_settings.CACHE_EMBEDDING_MAX_TEXT_CHARS = 4000
            mock_settings.RAG_EMBEDDING_DIMENSIONS = 1536

            first = await service.embed_texts(["hello"])
            second = await service.embed_texts(["hello"])

        self.assertEqual(first, [[0.1, 0.2]])
        self.assertEqual(second, [[0.1, 0.2]])
        service._adapter.embed_texts.assert_awaited_once_with(["hello"])
        cache_set.assert_awaited_once()
        self.assertEqual(cache_get.await_count, 2)

    async def test_embed_texts_skips_cache_for_overlong_text(self):
        from backend.lib.embedding_cache import embed_texts_with_cache

        embed_fn = AsyncMock(return_value=[[0.3, 0.4]])
        with (
            patch("backend.lib.embedding_cache.settings") as mock_settings,
            patch("backend.lib.embedding_cache.app_cache.get_many", AsyncMock()) as cache_get,
            patch("backend.lib.embedding_cache.app_cache.set_many", AsyncMock()) as cache_set,
        ):
            mock_settings.CACHE_EMBEDDING_MAX_TEXT_CHARS = 5
            mock_settings.RAG_EMBEDDING_DIMENSIONS = 1536
            vectors = await embed_texts_with_cache(
                provider="local",
                model="local-heuristic",
                texts=["0123456789"],
                embed_fn=embed_fn,
            )

        self.assertEqual(vectors, [[0.3, 0.4]])
        embed_fn.assert_awaited_once_with(["0123456789"])
        cache_get.assert_not_awaited()
        cache_set.assert_not_awaited()

    async def test_embedding_cache_deduplicates_and_batches_provider_calls(self):
        from backend.lib.embedding_cache import embed_texts_with_cache

        embed_fn = AsyncMock(
            side_effect=lambda batch: [[float(ord(text[0]))] for text in batch]
        )
        with (
            patch("backend.lib.embedding_cache.settings") as mock_settings,
            patch(
                "backend.lib.embedding_cache.app_cache.get_many", AsyncMock(return_value={})
            ),
            patch("backend.lib.embedding_cache.app_cache.set_many", AsyncMock()),
        ):
            mock_settings.CACHE_EMBEDDING_MAX_TEXT_CHARS = 4000
            mock_settings.CACHE_EMBEDDING_BATCH_SIZE = 2
            mock_settings.RAG_EMBEDDING_DIMENSIONS = 1536
            vectors = await embed_texts_with_cache(
                provider="local",
                model="local-heuristic",
                texts=["a", "b", "a", "c"],
                embed_fn=embed_fn,
            )

        self.assertEqual(vectors, [[97.0], [98.0], [97.0], [99.0]])
        self.assertEqual(embed_fn.await_args_list[0].args[0], ["a", "b"])
        self.assertEqual(embed_fn.await_args_list[1].args[0], ["c"])

    async def test_ai_embed_retrieval_queries_uses_cache(self):
        from backend.modules.ai.providers import AiProviderRegistry

        registry = AiProviderRegistry()
        provider = AsyncMock()
        provider.key = "local"
        provider.embed_texts = AsyncMock(return_value=[[0.5, 0.6]])
        registry.embedding_provider_and_model = MagicMock(
            return_value=(provider, "local-heuristic")
        )

        with (
            patch("backend.lib.embedding_cache.settings") as mock_settings,
            patch(
                "backend.lib.embedding_cache.app_cache.get_many",
                AsyncMock(
                    side_effect=[
                        {},
                        {embedding_cache_key("local", "local-heuristic", "hello"): [0.5, 0.6]},
                    ]
                ),
            ),
            patch("backend.lib.embedding_cache.app_cache.set_many", AsyncMock()) as cache_set,
        ):
            mock_settings.CACHE_EMBEDDING_TTL_SECONDS = 600
            mock_settings.CACHE_EMBEDDING_MAX_TEXT_CHARS = 4000
            mock_settings.RAG_EMBEDDING_DIMENSIONS = 1536

            first = await registry.embed_retrieval_queries(["hello"])
            second = await registry.embed_retrieval_queries(["hello"])

        self.assertEqual(first, [[0.5, 0.6]])
        self.assertEqual(second, [[0.5, 0.6]])
        provider.embed_texts.assert_awaited_once_with(["hello"], model="local-heuristic")
        cache_set.assert_awaited_once()
