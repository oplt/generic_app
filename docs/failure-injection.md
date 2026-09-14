# Failure injection and resilience testing (Phase 16)

Controlled fault harness for **local/test only**.

```text
FAILURE_INJECTION_ENABLED=false   # default
```

## Hard rules

* **Production forbidden** — `APP_ENV=production` rejects `FAILURE_INJECTION_ENABLED=true`
  at settings load, and `injecting(...)` raises `FailureInjectionForbidden`.
* Unit/CI tests enable faults via `injecting(...)` without flipping the env flag.
* Fault summaries never include credentials, SQL text, or request bodies.

## Usage

```python
from backend.lib.failure_injection import FaultKind, injecting, maybe_inject

with injecting(FaultKind.REDIS_TIMEOUT):
    value = await cache_get_json("ga:demo")  # fail-open → None
```

Fault catalog: `backend/lib/failure_injection/kinds.py`

| Area | Examples | Expected operational effect |
| --- | --- | --- |
| PostgreSQL | connection, slow query, pool exhausted, serialization | ready degraded/unavailable; no write fail-open |
| Redis | unavailable, timeout, cache miss storm | cache miss / ready unavailable |
| AI | timeout, 429, 500, malformed | bounded retries then fail; degraded under transient faults |
| Storage | upload/read/timeout | unavailable when required |
| Celery | worker failure, retry exhaustion, duplicate publish | errors or duplicate dispatch (idempotency must hold) |
| RAG | embedding failure, vector unavailable, stale index | degraded retrieval / readiness |
| Email | SMTP unavailable/timeout | delivery errors; effect ledger stays consistent |

## CI

Deterministic suite:

```text
backend/tests/test_failure_injection_resilience.py
backend/tests/test_dependency_degradation.py
```

Included in the normal backend pytest path used by GitHub Actions.

## Related

* [dependency-degradation.md](runbooks/dependency-degradation.md)
* [ai-rag-degraded-mode.md](runbooks/ai-rag-degraded-mode.md)
* Infra diagnostics: [diagnostics.md](diagnostics.md)
