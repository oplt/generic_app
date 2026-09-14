from __future__ import annotations

import asyncio
import logging
from time import perf_counter

import httpx
from backend.core.config import settings
from backend.lib.concurrency import bounded_gather, retry_async, run_with_timeout
from backend.lib.embedding_cache import embed_texts_with_cache
from backend.lib.vectors import can_index_embedding
from backend.modules.ai.provider_retry import ProviderTransportError
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.langchain_embeddings import LangChainEmbeddingAdapter
from backend.modules.rag.infrastructure.rag_config import RagConfig
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _is_non_retryable_http(exc: BaseException) -> bool:
    if isinstance(exc, HTTPException):
        return exc.status_code < 500 and exc.status_code != 429
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code < 500 and code != 429
    return False


def _retry_after_from_exc(exc: BaseException) -> str | float | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.headers.get("Retry-After")
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            return response.headers.get("Retry-After")
        except Exception:
            return None
    return None


class EmbeddingService:
    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig.from_settings()
        self._adapter = LangChainEmbeddingAdapter(self.config)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        from backend.lib.failure_injection import maybe_inject
        from backend.lib.failure_injection.kinds import FaultKind

        maybe_inject(FaultKind.RAG_EMBEDDING_FAILURE)
        maybe_inject(FaultKind.AI_EMBEDDING_PARTIAL)

        batch_size = max(
            1,
            int(
                getattr(self.config, "embedding_batch_size", 0)
                or settings.CACHE_EMBEDDING_BATCH_SIZE
                or 64
            ),
        )
        concurrency = max(1, int(getattr(self.config, "embedding_concurrency", 1) or 1))
        max_retries = max(0, int(getattr(self.config, "embedding_max_retries", 0) or 0))
        expected_dims = int(
            getattr(self.config, "embedding_dimensions", settings.RAG_EMBEDDING_DIMENSIONS)
        )
        deadline_seconds = max(1.0, float(settings.AI_REQUEST_TIMEOUT_SECONDS))
        started = perf_counter()

        async def _embed_batch(batch: list[str]) -> list[list[float]]:
            async def _once() -> list[list[float]]:
                try:
                    vectors = await embed_texts_with_cache(
                        provider=self.config.embedding_provider,
                        model=self.config.embedding_model,
                        texts=batch,
                        embed_fn=self._adapter.embed_texts,
                        dimensions=expected_dims,
                    )
                except Exception as exc:
                    if _is_non_retryable_http(exc):
                        # Wrap so retry_async treats it as non-retryable via ValueError path.
                        raise ValueError(str(exc)) from exc
                    raise
                self._validate_vectors(vectors, expected=len(batch), dimensions=expected_dims)
                return vectors

            return await retry_async(
                _once,
                max_attempts=max_retries + 1,
                base_delay_seconds=0.5,
                max_delay_seconds=min(30.0, deadline_seconds),
                jitter_seconds=0.25,
                idempotent=True,
                kind="rag_embedding",
                retryable_exceptions=(
                    TimeoutError,
                    ConnectionError,
                    OSError,
                    httpx.TransportError,
                    httpx.TimeoutException,
                    ProviderTransportError,
                    Exception,
                ),
                non_retryable_exceptions=(
                    ValueError,
                    TypeError,
                    AssertionError,
                    asyncio.CancelledError,
                ),
                retry_after_from_exc=_retry_after_from_exc,
            )

        async def _run_batches() -> list[list[float]]:
            if len(texts) <= batch_size and concurrency == 1:
                return await _embed_batch(texts)

            batches = [
                texts[start : start + batch_size] for start in range(0, len(texts), batch_size)
            ]
            results = await bounded_gather(
                [_embed_batch(batch) for batch in batches],
                limit=concurrency,
                return_exceptions=True,
                kind="rag_embedding_batches",
            )
            vectors: list[list[float]] = []
            for index, result in enumerate(results):
                if isinstance(result, BaseException):
                    # Never substitute zero vectors for failed embeddings.
                    if getattr(self.config, "embedding_allow_partial_failure", False):
                        logger.error(
                            "Embedding batch %s/%s failed; partial-failure mode no longer "
                            "fills zeros — failing the indexing unit",
                            index + 1,
                            len(batches),
                            exc_info=result,
                        )
                    raise result
                vectors.extend(result)
            if len(vectors) != len(texts):
                raise RuntimeError("Embedding batching returned an unexpected vector count")
            return vectors

        try:
            vectors = await run_with_timeout(
                _run_batches(),
                timeout_seconds=deadline_seconds,
                kind="rag_embedding",
            )
        except TimeoutError as exc:
            raise TimeoutError("RAG embedding deadline exceeded") from exc

        metrics.rag_embedding_latency_ms.observe((perf_counter() - started) * 1000)
        return vectors

    @staticmethod
    def _validate_vectors(
        vectors: list[list[float]],
        *,
        expected: int,
        dimensions: int,
    ) -> None:
        if len(vectors) != expected:
            raise ValueError(
                f"Embedding provider returned {len(vectors)} vectors, expected {expected}"
            )
        for index, vector in enumerate(vectors):
            if not can_index_embedding(vector, expected_dimensions=dimensions):
                raise ValueError(
                    f"Invalid embedding at batch index {index}: "
                    f"expected {dimensions} finite non-zero-norm dimensions"
                )
