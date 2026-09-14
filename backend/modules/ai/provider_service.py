from __future__ import annotations

from functools import lru_cache

from backend.core.config import settings
from backend.modules.ai.base_service import AiBaseService
from backend.modules.ai.schemas import AiProviderDescriptor


class AiProviderService(AiBaseService):
    @staticmethod
    def list_provider_descriptors() -> list[AiProviderDescriptor]:
        return [AiProviderDescriptor(**item) for item in _provider_capabilities(
            settings.AI_EMBEDDING_PROVIDER
        )]


@lru_cache(maxsize=8)
def _provider_capabilities(embedding_provider: str) -> tuple[dict[str, object], ...]:
    return (
        {
            "key": "local",
            "label": "Local heuristic",
            "supports_generation": True,
            "supports_embeddings": True,
        },
        {
            "key": "openai",
            "label": "OpenAI",
            "supports_generation": True,
            "supports_embeddings": True,
        },
        {
            "key": "anthropic",
            "label": "Anthropic",
            "supports_generation": True,
            "supports_embeddings": embedding_provider == "anthropic",
        },
    )
