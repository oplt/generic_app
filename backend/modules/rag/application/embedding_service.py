from __future__ import annotations

import logging
from time import perf_counter

from backend.core.config import settings
from backend.lib.concurrency import bounded_gather
from backend.lib.embedding_cache import embed_texts_with_cache
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.langchain_embeddings import LangChainEmbeddingAdapter
from backend.modules.rag.infrastructure.rag_config import RagConfig

logger = logging.getLogger(__name__)


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
        started = perf_counter()

        async def _embed_batch(batch: list[str]) -> list[list[float]]:
            attempt = 0
            while True:
                try:
                    return await embed_texts_with_cache(
                        provider=self.config.embedding_provider,
                        model=self.config.embedding_model,
                        texts=batch,
                        embed_fn=self._adapter.embed_texts,
                        dimensions=getattr(
                            self.config,
                            "embedding_dimensions",
                            settings.RAG_EMBEDDING_DIMENSIONS,
                        ),
                    )
                except Exception:
                    if attempt >= max_retries:
                        raise
                    attempt += 1
                    logger.warning(
                        "Embedding batch failed (attempt %s/%s); retrying",
                        attempt,
                        max_retries,
                    )

        if len(texts) <= batch_size and concurrency == 1:
            vectors = await _embed_batch(texts)
            metrics.rag_embedding_latency_ms.observe((perf_counter() - started) * 1000)
            return vectors

        batches = [texts[start : start + batch_size] for start in range(0, len(texts), batch_size)]
        results = await bounded_gather(
            [_embed_batch(batch) for batch in batches],
            limit=concurrency,
            return_exceptions=True,
            kind="rag_embedding_batches",
        )
        vectors: list[list[float]] = []
        failures = 0
        for index, result in enumerate(results):
            if isinstance(result, BaseException):
                failures += 1
                if getattr(self.config, "embedding_allow_partial_failure", False):
                    logger.error(
                        "Embedding batch %s/%s failed; filling zeros for partial failure",
                        index + 1,
                        len(batches),
                        exc_info=result,
                    )
                    dim = int(
                        getattr(
                            self.config,
                            "embedding_dimensions",
                            settings.RAG_EMBEDDING_DIMENSIONS,
                        )
                    )
                    vectors.extend([[0.0] * dim for _ in batches[index]])
                    continue
                raise result
            vectors.extend(result)
        if failures and getattr(self.config, "embedding_allow_partial_failure", False):
            logger.warning(
                "Completed embeddings with %s failed batch(es) under partial-failure mode",
                failures,
            )
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding batching returned an unexpected vector count")
        metrics.rag_embedding_latency_ms.observe((perf_counter() - started) * 1000)
        return vectors
