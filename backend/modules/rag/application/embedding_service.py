from __future__ import annotations

from time import perf_counter

from backend.core.config import settings
from backend.lib.embedding_cache import embed_texts_with_cache
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.langchain_embeddings import LangChainEmbeddingAdapter
from backend.modules.rag.infrastructure.rag_config import RagConfig


class EmbeddingService:
    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig.from_settings()
        self._adapter = LangChainEmbeddingAdapter(self.config)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        started = perf_counter()
        vectors = await embed_texts_with_cache(
            provider=self.config.embedding_provider,
            model=self.config.embedding_model,
            texts=texts,
            embed_fn=self._adapter.embed_texts,
            dimensions=getattr(
                self.config, "embedding_dimensions", settings.RAG_EMBEDDING_DIMENSIONS
            ),
        )
        metrics.rag_embedding_latency_ms.observe((perf_counter() - started) * 1000)
        return vectors
