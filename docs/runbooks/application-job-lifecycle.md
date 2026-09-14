# Application job lifecycle

Celery deliveries are at-least-once. `application_jobs` is the durable record for one
logical worker operation across retries, worker loss, and queue delay.

## States

| Status | Meaning |
| --- | --- |
| `queued` | Enqueued or released for retry; not currently executing |
| `running` | Claimed by a worker |
| `succeeded` | Terminal success; later deliveries with the same `operation_id` are no-ops |
| `failed` | Attempt failed and may still be retryable |
| `dead_letter` | Attempts exhausted, deadline passed, or non-retryable failure |

## Contract

1. Producers that know a stable key call `ensure_queued_job(...)` before `apply_async`
   (email queue, outbox → RAG indexing). That stamps `available_at` for queue latency.
2. Workers enter through `run_tracked_sync(..., operation_id=...)`, which locks one row,
   increments `attempts`, sets `started_at`, and observes `worker_job_queue_latency_seconds`.
3. Stale `running` rows older than `WORKER_JOB_RUNNING_LEASE_SECONDS` may be reclaimed
   (worker-lost / kill -9 before finish).
4. `ExternalEffectInFlightError` returns the job to `queued` with a deferred `available_at`
   instead of forging a terminal failure.
5. Scheduled beat jobs (`outbox-dispatch`, `chat-retention`) omit `operation_id` so each
   tick is a new logical job. Overlapping ticks are suppressed with Redis NX schedule locks
   (`worker_beat_schedule_lock_total`); chat retention also takes a Postgres advisory
   transaction lock. See [dependency-degradation.md](./dependency-degradation.md).

## Metrics

- `worker_jobs_total{job_type,outcome}` — success / failure / deferred / deduplicated / …
- `worker_job_duration_seconds{job_type}` — claim-to-finish wall time
- `worker_job_queue_latency_seconds{job_type}` — `started_at - available_at`
- `worker_job_retries_total{job_type}` — increments when `attempts > 1` on a run

## Dashboard query sketch

```sql
SELECT job_type, status, attempts, max_attempts,
       EXTRACT(EPOCH FROM (started_at - available_at)) AS queue_latency_seconds,
       EXTRACT(EPOCH FROM (finished_at - started_at)) AS run_seconds,
       last_error, operation_id, correlation_id
FROM application_jobs
WHERE created_at > now() - interval '24 hours'
ORDER BY created_at DESC;
```

## Operator console

Admin aggregation UI: [`docs/jobs-console.md`](../jobs-console.md) (`/admin/jobs`).

## Tests

`backend/tests/test_application_job_lifecycle.py` covers success-after-retry, dead-letter,
stale running reclaim, queue latency, dedupe, and deadline expiry.
