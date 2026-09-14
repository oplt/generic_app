from prometheus_client import Counter, Histogram

ai_run_latency_ms = Histogram(
    "ai_run_latency_ms",
    "AI provider generation latency in milliseconds",
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000),
)
ai_run_failed_total = Counter("ai_run_failed_total", "AI provider generation failures")
ai_provider_request_total = Counter(
    "ai_provider_request_total",
    "AI provider HTTP requests",
    labelnames=("provider", "operation", "outcome"),
)
ai_provider_retry_total = Counter(
    "ai_provider_retry_total",
    "AI provider retries",
    labelnames=("provider", "operation", "reason"),
)
ai_provider_timeout_total = Counter(
    "ai_provider_timeout_total",
    "AI provider deadline/timeout failures",
    labelnames=("provider", "operation"),
)
agent_run_latency_ms = Histogram(
    "agent_run_latency_ms",
    "End-to-end agent run latency in milliseconds",
    buckets=(100, 250, 500, 1000, 2500, 5000, 10000, 30000),
)
agent_context_degraded_total = Counter(
    "agent_context_degraded_total",
    "Agent context degradation events",
    labelnames=("source",),
)
