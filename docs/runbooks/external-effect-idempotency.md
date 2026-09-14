# External effect idempotency

Celery is configured for at-least-once delivery (`task_acks_late`,
`task_reject_on_worker_lost`). Non-idempotent consumers such as email therefore
need a durable operation key and an effect ledger.

## Contract

1. Producers assign a stable `operation_id` before `apply_async` (auth emails use
   `email:verify:{user_id}:{token_hash}` / `email:reset:...`; generic queueing
   generates `email:{uuid}`).
2. `run_tracked_sync` stores one `application_jobs` row per `operation_id` and
   increments `attempts` on resume instead of creating a new logical job.
3. `external_effects` records the externally visible side effect:
   - `succeeded` → duplicate deliveries skip the provider
   - fresh `in_flight` → deferred until `EXTERNAL_EFFECT_LEASE_SECONDS`
   - stale `in_flight` or `failed` → reclaim and retry
4. SMTP messages carry a stable `Message-ID` derived from the operation id so a
   reclaim after the crash gap still counts as one provider-visible effect when
   the provider honors idempotency keys.

## Crash boundaries

| Kill point | Ledger state | Next delivery |
| --- | --- | --- |
| Before provider accept (exception) | `failed` | Reclaim and send once |
| After provider accept, before ack | `in_flight` | Defer until lease, then reclaim; Message-ID bounds visibility |
| After success ack | `succeeded` | No provider call |

Focused unit tests live in `backend/tests/test_external_effect_idempotency.py`.
