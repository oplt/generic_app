# Dependency degradation and scheduled-job overlap

This runbook documents how the API and workers behave when dependencies fail, and how
overlapping Celery beat ticks stay safe.

## Operational states

| Readiness check value | `dependency_states` | Meaning |
| --- | --- | --- |
| `ok` | `healthy` | Dependency answered the probe |
| `error` | `unavailable` | Probe failed; traffic that requires it must not be accepted as ready |
| `not_required` | `not_required` | Feature off (e.g. storage/vector when RAG disabled) |
| `unknown` | `unknown` | Not probed (legacy); required checks treat this as failure |

`/health/live` always returns OK (process up). `/health/ready` returns 200 only when every
required check is `ok`; otherwise 503 with `status: degraded`, per-check values, and
`dependency_states`.

Required checks: `db`, `redis`, `queue`, plus `storage` when RAG or a bucket is configured,
plus `vector` when RAG is enabled.

## Dependency matrix

| Dependency | Healthy | Degraded / fail-open | Unavailable | Recovery |
| --- | --- | --- | --- | --- |
| PostgreSQL | Sessions, outbox, jobs, RAG | N/A (no fail-open for writes) | Ready=503; workers error and bounded-retry or dead-letter | Restore DB; reclaim stale job/outbox leases |
| Redis | Cache, rate limits, beat locks, Celery broker | Cache reads return miss; rate limit uses bounded local fallback; beat locks fail-open | Ready=503; broker publish fails → outbox retries with lease | Restore Redis; local rate-limit map is process-scoped only |
| Object storage (S3/MinIO) | Document bytes | Not required when RAG/bucket off | Ready=503 when required; uploads fail before durable commit paths | Restore bucket/credentials; reconcile orphan objects |
| pgvector | Retrieval + readiness | Explicit RAG degraded outcomes (no JSON similarity fallback) | Ready=503 when RAG on; retrieval reports degradation | Repair extension/index/dimensions; re-index |
| AI provider | Generation | Bounded retries (`AI_PROVIDER_MAX_RETRIES` + backoff/jitter) then fail | Chat/AI endpoints error; no unbounded retry storm | Restore provider; confirm timeout settings |
| Celery workers / queue | Heartbeat + depth metrics | Queue lag visible in ready `details.queue_metrics` | Ready=503 when queue probe fails | Scale/restart workers; reclaim `application_jobs` running leases |

Related detail: [ai-rag-degraded-mode.md](./ai-rag-degraded-mode.md),
[outbox-dispatch.md](./outbox-dispatch.md),
[application-job-lifecycle.md](./application-job-lifecycle.md).

## Beat schedule overlap

| Schedule | Interval | Overlap controls |
| --- | --- | --- |
| `dispatch-background-job-outbox` | 30s | Redis NX lock (`WORKER_BEAT_OUTBOX_LOCK_TTL_SECONDS`, released on finish); fail-open if Redis down. Rows claimed with `FOR UPDATE SKIP LOCKED` + `lease_token`. |
| `cleanup-expired-chat-conversations` | 1h | Redis NX lock (`WORKER_BEAT_CHAT_RETENTION_LOCK_TTL_SECONDS`); Postgres `pg_try_advisory_xact_lock` inside the delete transaction. |

Metrics: `worker_beat_schedule_lock_total{schedule,backend,outcome}` where `outcome` is
`acquired`, `skipped`, or `redis_error`.

Overlapping ticks must not create unbounded Celery fan-out: beat tasks use
`max_attempts=1` / `retryable=False` for the logical job record, and outbox/ingestion
retain their own lease and attempt ceilings.

## Failure-injection validation

Use the Phase 16 harness (`docs/failure-injection.md`) for deterministic local/CI
faults. Never enable `FAILURE_INJECTION_ENABLED` in production.

In an isolated Compose stack (or via `injecting(...)` in tests):

1. **Redis down** — ready=503; cache get returns miss; rate limit stays bounded via local
   fallback; concurrent outbox ticks still safe via SKIP LOCKED; retention exclusivity via
   advisory lock.
2. **Postgres down** — ready=503; workers fail without opening extra pools beyond configured
   `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`.
3. **Concurrent beat** — invoke `dispatch_outbox_task` / `cleanup_chat_retention_task` twice
   in parallel; expect one Redis acquire and one skip (or dual proceed only when Redis is
   down, with Postgres/outbox exclusivity still holding).
4. **Provider timeout** — confirm retries stop at `AI_PROVIDER_MAX_RETRIES` and request
   timeouts remain finite (`FaultKind.AI_TIMEOUT`).
5. **Storage / email / RAG** — upload/SMTP/vector faults surface as unavailable or explicit
   RAG degradation reasons without leaking secrets.
6. **Recovery** — restore dependency; ready returns 200; degradation counters stop climbing.

Focused unit coverage:

* `backend/tests/test_dependency_degradation.py`
* `backend/tests/test_failure_injection_resilience.py`

Admin aggregation of live dependency status: [`docs/diagnostics.md`](../diagnostics.md).
