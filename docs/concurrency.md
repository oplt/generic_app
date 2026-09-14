# Concurrency and backpressure

Shared async helpers live in `backend/lib/concurrency.py`. Prefer them over
unbounded `asyncio.gather` on large or external-IO workloads.

## API

```python
from backend.lib.concurrency import (
    LoopLocalLimiter,
    bounded_gather,
    map_concurrently,
    retry_async,
    run_with_timeout,
)

results = await map_concurrently(items, worker, limit=4, kind="memory_write")
await run_with_timeout(coro, timeout_seconds=2.0, kind="memory_search")
await retry_async(
    load,
    max_attempts=3,
    idempotent=True,
    retryable_exceptions=(TimeoutError, ConnectionError),
    non_retryable_exceptions=(ValueError, PermissionError),
    kind="provider",
)
```

| Helper | Use when |
| --- | --- |
| `map_concurrently` | Same worker over many items; slots acquired before work starts |
| `bounded_gather` | Existing awaitables need a concurrency cap |
| `run_with_timeout` | Hard deadline with cancellation |
| `retry_async` | Idempotent ops only; selective exception classes |
| `LoopLocalLimiter` | Process-wide per-loop semaphore (providers, search) |
| `backoff_delay` | Shared exponential backoff + Retry-After + jitter |

## Rules

- Do not auto-retry when `idempotent=False` (raises `RetryNotAllowedError`).
- Do not retry validation/authorization/deterministic failures — list them in
  `non_retryable_exceptions`.
- Keep Prometheus `kind` labels low-cardinality (feature names, not IDs).

## Adopted call sites

- Memory turn writes → `map_concurrently`
- Memory search/list → `run_with_timeout` / `bounded_gather`
- RAG hybrid retrieve → `bounded_gather`
- Chat provider + web search slots → `LoopLocalLimiter`
- AI `provider_retry` → `LoopLocalLimiter` + `backoff_delay`

## Metrics

- `concurrency_wait_seconds{kind}`
- `concurrency_operation_latency_seconds{kind,operation}`
- `concurrency_retries_total{kind,outcome}`
- `concurrency_timeouts_total{kind,operation}`
