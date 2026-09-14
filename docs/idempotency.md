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

Scope is per user (optional org), endpoint name, and key. The request fingerprint
covers JSON body **and** URL path/query so empty-body path mutations (index/retry)
cannot replay across different resource ids. Claims use a unique constraint plus
`SELECT … FOR UPDATE` (not check-then-insert alone).

Config: `IDEMPOTENCY_TTL_SECONDS`, `IDEMPOTENCY_LEASE_SECONDS`,
`IDEMPOTENCY_WAIT_SECONDS`.

Idempotency is **not** a substitute for database uniqueness constraints.

## Adoption matrix (mutating HTTP)

Legend:

- **REQUIRED** — clients should always send `Idempotency-Key` (server may still accept without for back-compat when `required=False`)
- **OPTIONAL** — key accepted; safe default without key
- **UNIQUE** — DB/unique constraint or natural identity already prevents duplicates
- **N/A** — read-only, delete-by-id, or multipart where body fingerprinting is unreliable

| Endpoint | Decision | Endpoint key | Notes |
| --- | --- | --- | --- |
| `POST /projects` | OPTIONAL (recommended) | `projects.create` | Adopted |
| `POST /api-keys` | OPTIONAL (recommended) | `platform.api_keys.create` | Avoids duplicate plaintext keys on retry |
| `POST /rag/documents/upload` | N/A (multipart) | — | Prefer client-side de-dupe + content fingerprint; multipart body hashes are unstable |
| `POST /rag/documents/{id}/index` | OPTIONAL | `rag.document.index` | Duplicate enqueue risk |
| `POST /rag/documents/{id}/reindex` | OPTIONAL | `rag.document.reindex` | Alias of index |
| `POST /rag/jobs/{id}/retry` | OPTIONAL | `rag.ingestion.retry` | Fresh attempt side effect |
| `POST /rag/admin/reindex-stale` | OPTIONAL | `rag.reindex_stale` | Bulk enqueue |
| `POST /rag/admin/index-versions` | OPTIONAL | `rag.index_version.create` | Creates building version |
| `POST /rag/admin/index-versions/{id}/activate` | OPTIONAL | `rag.index_version.activate` | Activation side effect |
| `POST /rag/admin/index-versions/{id}/rollback` | OPTIONAL | `rag.index_version.rollback` | Rollback without re-embed |
| `POST /rag/admin/evaluation/.../runs` | OPTIONAL | `rag.evaluation.run` | Expensive embed/retrieve run |
| `POST /admin/jobs/{id}/retry` | OPTIONAL | `jobs.console.retry` | Worker re-dispatch |
| `POST /admin/jobs/{id}/cancel` | UNIQUE / N/A | — | Cancel is idempotent at domain level |
| Webhooks / billing provider calls | REQUIRED (when added) | TBD | Pair with effect ledger |
| AI provider chat completions | UNIQUE + ledger | — | Provider/run ids; not HTTP Idempotency-Key layer |

Protected endpoints above use `required=False` so existing clients keep working; send
`Idempotency-Key` for safe retries.

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
