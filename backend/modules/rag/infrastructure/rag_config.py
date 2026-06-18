from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import settings


@dataclass(frozen=True, slots=True)
class RagConfig:
    enabled: bool
    vector_backend: str
    embedding_provider: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    score_threshold: float
    max_context_tokens: int
    allowed_file_types: tuple[str, ...]
    max_file_bytes: int

    @classmethod
    def from_settings(cls) -> RagConfig:
        raw_types = settings.RAG_ALLOWED_FILE_TYPES.strip()
        allowed = tuple(t.strip().lower() for t in raw_types.split(",") if t.strip())
        return cls(
            enabled=settings.RAG_ENABLED,
            vector_backend=settings.RAG_VECTOR_BACKEND.lower(),
            embedding_provider=settings.RAG_EMBEDDING_PROVIDER.lower(),
            embedding_model=settings.RAG_EMBEDDING_MODEL,
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            top_k=settings.RAG_TOP_K,
            score_threshold=settings.RAG_SCORE_THRESHOLD,
            max_context_tokens=settings.RAG_MAX_CONTEXT_TOKENS,
            allowed_file_types=allowed or ("pdf", "txt", "md", "docx", "csv"),
            max_file_bytes=settings.RAG_MAX_FILE_BYTES,
        )
