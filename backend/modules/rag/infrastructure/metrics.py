"""Prometheus metrics for the RAG module."""

from prometheus_client import Counter, Histogram

rag_document_upload_total = Counter("rag_document_upload_total", "Document uploads")
rag_parse_success_total = Counter("rag_parse_success_total", "Successful document parses")
rag_parse_failure_total = Counter("rag_parse_failure_total", "Failed document parses")
rag_chunk_count = Histogram(
    "rag_chunk_count",
    "Chunks produced per document",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500),
)
rag_embedding_latency_ms = Histogram(
    "rag_embedding_latency_ms",
    "Embedding latency in milliseconds",
    buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000),
)
rag_vector_upsert_success_total = Counter("rag_vector_upsert_success_total", "Vector upserts")
rag_vector_upsert_failure_total = Counter(
    "rag_vector_upsert_failure_total",
    "Vector upsert failures",
)
rag_retrieval_latency_ms = Histogram(
    "rag_retrieval_latency_ms",
    "Retrieval latency in milliseconds",
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000),
)
rag_retrieved_chunks = Histogram(
    "rag_retrieved_chunks",
    "Chunks retrieved per query",
    buckets=(0, 1, 2, 3, 5, 10, 20),
)
rag_answer_latency_ms = Histogram(
    "rag_answer_latency_ms",
    "RAG answer latency in milliseconds",
    buckets=(100, 250, 500, 1000, 2500, 5000, 10000),
)
rag_permission_denied_total = Counter("rag_permission_denied_total", "RAG permission denials")
rag_vector_unavailable_total = Counter("rag_vector_unavailable_total", "Vector store unavailable")
