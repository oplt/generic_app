from __future__ import annotations

from time import perf_counter

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
        embeddings = await self._adapter.embed_texts(texts)
        metrics.rag_embedding_latency_ms.observe((perf_counter() - started) * 1000)
        return embeddings
