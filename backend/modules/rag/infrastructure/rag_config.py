from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import settings
from backend.modules.rag.application.candidate_expansion import (
    RETRIEVAL_STRATEGIES,
    normalize_retrieval_strategy,
)
from backend.modules.rag.application.rerankers import (
    RERANKER_BACKENDS,
    normalize_reranker_backend,
)

SUPPORTED_VECTOR_BACKENDS = frozenset({"pgvector"})
RAG_VECTOR_DIMENSIONS = 1536


@dataclass(frozen=True, slots=True)
class RagConfig:
    enabled: bool
    vector_backend: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    chunk_size: int
    chunk_overlap: int
    top_k: int
    score_threshold: float
    max_context_tokens: int
    allowed_file_types: tuple[str, ...]
    max_file_bytes: int
    parser_timeout_seconds: float = 60.0
    retrieval_strategy: str = "hybrid_rrf"
    vector_candidate_count: int = 0
    lexical_candidate_count: int = 0
    rrf_k: int = 60
    rerank_enabled: bool = False
    rerank_candidate_multiplier: int = 3
    reranker_backend: str = "lightweight"
    document_aware_chunking: bool = False
    parent_child_chunking: bool = False
    parent_child_child_size: int = 200
    parent_child_child_overlap: int = 40
    parent_child_retrieval_enabled: bool = False
    dedup_exact_enabled: bool = False
    dedup_near_enabled: bool = False
    dedup_near_threshold: float = 0.9
    per_document_limit: int = 0
    mmr_enabled: bool = False
    mmr_lambda: float = 0.7
    neighbor_expansion_enabled: bool = False
    neighbor_window: int = 1
    embedding_batch_size: int = 64
    embedding_concurrency: int = 1
    embedding_max_retries: int = 2
    embedding_allow_partial_failure: bool = False

    @classmethod
    def from_settings(cls) -> RagConfig:
        raw_types = settings.RAG_ALLOWED_FILE_TYPES.strip()
        allowed = tuple(t.strip().lower() for t in raw_types.split(",") if t.strip())
        embedding_provider = (
            settings.RAG_EMBEDDING_PROVIDER.strip() or settings.AI_EMBEDDING_PROVIDER
        ).lower()
        return cls(
            enabled=settings.RAG_ENABLED,
            vector_backend=settings.RAG_VECTOR_BACKEND.lower(),
            embedding_provider=embedding_provider,
            embedding_model=settings.RAG_EMBEDDING_MODEL,
            embedding_dimensions=settings.RAG_EMBEDDING_DIMENSIONS,
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            top_k=settings.RAG_TOP_K,
            score_threshold=settings.RAG_SCORE_THRESHOLD,
            retrieval_strategy=normalize_retrieval_strategy(settings.RAG_RETRIEVAL_STRATEGY),
            vector_candidate_count=max(0, settings.RAG_VECTOR_CANDIDATE_COUNT),
            lexical_candidate_count=max(0, settings.RAG_LEXICAL_CANDIDATE_COUNT),
            rrf_k=max(1, settings.RAG_RRF_K),
            rerank_enabled=settings.RAG_RERANK_ENABLED,
            rerank_candidate_multiplier=max(1, settings.RAG_RERANK_CANDIDATE_MULTIPLIER),
            reranker_backend=normalize_reranker_backend(settings.RAG_RERANKER_BACKEND),
            document_aware_chunking=settings.RAG_DOCUMENT_AWARE_CHUNKING,
            parent_child_chunking=settings.RAG_PARENT_CHILD_CHUNKING,
            parent_child_child_size=max(32, settings.RAG_PARENT_CHILD_CHILD_SIZE),
            parent_child_child_overlap=max(0, settings.RAG_PARENT_CHILD_CHILD_OVERLAP),
            parent_child_retrieval_enabled=settings.RAG_PARENT_CHILD_RETRIEVAL,
            dedup_exact_enabled=settings.RAG_DEDUP_EXACT,
            dedup_near_enabled=settings.RAG_DEDUP_NEAR,
            dedup_near_threshold=settings.RAG_DEDUP_NEAR_THRESHOLD,
            per_document_limit=max(0, settings.RAG_PER_DOCUMENT_LIMIT),
            mmr_enabled=settings.RAG_MMR_ENABLED,
            mmr_lambda=settings.RAG_MMR_LAMBDA,
            neighbor_expansion_enabled=settings.RAG_NEIGHBOR_EXPANSION,
            neighbor_window=max(0, settings.RAG_NEIGHBOR_WINDOW),
            embedding_batch_size=max(1, settings.RAG_EMBEDDING_BATCH_SIZE),
            embedding_concurrency=max(1, settings.RAG_EMBEDDING_CONCURRENCY),
            embedding_max_retries=max(0, settings.RAG_EMBEDDING_MAX_RETRIES),
            embedding_allow_partial_failure=settings.RAG_EMBEDDING_ALLOW_PARTIAL_FAILURE,
            max_context_tokens=settings.RAG_MAX_CONTEXT_TOKENS,
            allowed_file_types=allowed or ("pdf", "txt", "md", "docx", "csv"),
            max_file_bytes=settings.RAG_MAX_FILE_BYTES,
            parser_timeout_seconds=settings.RAG_PARSER_TIMEOUT_SECONDS,
        )


def validate_rag_config(config: RagConfig | None = None) -> None:
    """Fail fast when RAG is enabled with an unsupported vector backend."""
    resolved = config or RagConfig.from_settings()
    if not resolved.enabled:
        return
    if resolved.retrieval_strategy not in RETRIEVAL_STRATEGIES:
        raise RuntimeError(
            f"RAG_RETRIEVAL_STRATEGY={resolved.retrieval_strategy!r} is not supported. "
            f"Expected one of: {', '.join(sorted(RETRIEVAL_STRATEGIES))}."
        )
    if resolved.reranker_backend not in RERANKER_BACKENDS:
        raise RuntimeError(
            f"RAG_RERANKER_BACKEND={resolved.reranker_backend!r} is not supported. "
            f"Expected one of: {', '.join(sorted(RERANKER_BACKENDS))}."
        )
    if (
        resolved.vector_backend in SUPPORTED_VECTOR_BACKENDS
        and resolved.embedding_dimensions == RAG_VECTOR_DIMENSIONS
    ):
        return
    if resolved.vector_backend == "pgvector":
        raise RuntimeError(
            f"RAG_EMBEDDING_DIMENSIONS={resolved.embedding_dimensions} is incompatible with "
            f"the pgvector schema ({RAG_VECTOR_DIMENSIONS})."
        )
    supported = ", ".join(sorted(SUPPORTED_VECTOR_BACKENDS))
    raise RuntimeError(
        f"RAG_VECTOR_BACKEND={resolved.vector_backend!r} is not implemented. "
        f"Supported backends: {supported}."
    )
