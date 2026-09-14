# Operational jobs console (Phase 13)

Admin UI: `/admin/jobs`  
API prefix: `/api/v1/admin/jobs`

Aggregates durable `application_jobs` rows with RAG `rag_ingestion_jobs` into one
operator view. Does **not** expose Celery arbitrary invoke or secret payloads.

## Authorization

| Permission | Actions |
| --- | --- |
| `jobs.read` | List + detail |
| `jobs.retry` | Retry (RAG ingestion only) |
| `jobs.cancel` | Cancel queued/pending jobs |

System admins receive all permissions via catalog bootstrap. Org admins / project
editors include `jobs.cancel` after migration `l2b9d4e5f150`.

## Console states

| State | Meaning |
| --- | --- |
| `queued` | Waiting to run |
| `running` | Actively claimed / heartbeat fresh |
| `retrying` | Queued again with future `available_at` |
| `succeeded` | Terminal success |
| `failed` | Failed or dead-lettered |
| `cancelled` | Operator cancelled before start |
| `stale` | Running past lease / heartbeat (worker likely lost) |

Filters: status, job type, queue, project (RAG), date range, failures/stale.

## Safe actions

* **Retry** — only RAG ingestion jobs (creates a fresh outbox attempt via existing
  ingestion service). Application email / beat jobs are not re-dispatched from UI
  because stored payloads are intentionally redacted to field names.
* **Cancel** — queued `application_jobs` → `cancelled`; pending RAG jobs →
  `cancelled` and matching outbox rows marked cancelled.

## Redaction

Payload summaries return `field_names` only. Names matching
password/secret/token/api_key/credential/cookie patterns are dropped.

## Related

* Lifecycle: [runbooks/application-job-lifecycle.md](runbooks/application-job-lifecycle.md)
* RAG job APIs remain at `/api/v1/rag/jobs*` for end-user scoped access
