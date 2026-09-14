"""Low-cardinality Prometheus metrics for document and general chat."""

from prometheus_client import Counter, Histogram

chat_requests_total = Counter(
    "chat_requests_total",
    "Chat answers by requested mode, selected route, and outcome",
    ["requested_mode", "route", "outcome"],
)
chat_route_total = Counter(
    "chat_route_total",
    "Chat route decisions by bounded reason",
    ["requested_mode", "route", "reason"],
)
chat_response_latency_ms = Histogram(
    "chat_response_latency_ms",
    "Completed chat response latency in milliseconds",
    ["route"],
    buckets=(100, 250, 500, 1000, 2500, 5000, 10000, 30000),
)
chat_sources_total = Counter(
    "chat_sources_total",
    "Persisted chat sources by kind",
    ["kind"],
)
chat_source_count = Histogram(
    "chat_source_count",
    "Sources attached to a completed answer by kind",
    ["kind"],
    buckets=(0, 1, 2, 3, 5, 10, 20),
)
chat_tokens_total = Counter(
    "chat_tokens_total",
    "Estimated output tokens by route",
    ["route"],
)
chat_errors_total = Counter(
    "chat_errors_total",
    "Chat errors by safe error code and route",
    ["code", "route"],
)
chat_stream_events_total = Counter(
    "chat_stream_events_total",
    "Chat SSE events by event type",
    ["event"],
)
chat_memory_recall_total = Counter(
    "chat_memory_recall_total",
    "Memory recall outcomes used by chat",
    ["outcome"],
)
