# Idempotency framework

Reusable HTTP `Idempotency-Key` support and Celery effect helpers live in
`backend/lib/idempotency/`. Celery email delivery continues to use the durable
`external_effects` ledger (see [external-effect-idempotency.md](runbooks/external-effect-idempotency.md)).

## HTTP

Opt in on mutating routes:

```python
from backend.lib.idempotency import Idempotency, IdempotencySession

@router.post("")
async def create_...(
    payload: ...,
    idem: IdempotencySession = Depends(Idempotency("projects.create", required=False)),
):
    return await idem.execute(
        _create,
        status_code=201,
        dump=lambda response: response.model_dump(mode="json"),
    )
```

Behavior:

| Case | Result |
| --- | --- |
| First request | `PROCESS` — run handler, store response |
| Same key + same body | Replay stored response |
| Same key + different body | `409 idempotency_key_conflict` |
| Concurrent same key | One runner; waiters replay or `409 idempotency_key_in_progress` |

Scope is per user (optional org), endpoint name, and key. Claims use a unique
constraint plus `SELECT … FOR UPDATE` (not check-then-insert alone).

Config: `IDEMPOTENCY_TTL_SECONDS`, `IDEMPOTENCY_LEASE_SECONDS`,
`IDEMPOTENCY_WAIT_SECONDS`.

Adopted: `POST /projects` (`projects.create`) when `Idempotency-Key` is present.

## Celery

```python
from backend.lib.idempotency import celery_operation_key, run_with_effect_idempotency

await run_with_effect_idempotency(
    operation_id=celery_operation_key("email", user_id, token_hash),
    effect_type="email",
    payload_parts=(to, subject, html, text),
    execute=lambda provider_key: deliver(..., message_id=provider_key),
)
```

`send_email` uses this helper over `begin_external_effect` /
`complete_external_effect`.

## Cleanup

Beat task `cleanup_idempotency_records_task` deletes expired
`idempotency_records` every 15 minutes.

Migration: `g7c4e2a9b815_add_idempotency_records.py`.
