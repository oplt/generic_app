# Transaction ownership

Rule of thumb for write paths:

```text
service / use-case owns the business transaction
dependency owns session lifecycle (get_db)
external side effects happen after commit, or via outbox / effect ledger
```

Avoid holding an open DB transaction across remote HTTP, SMTP, embedding, or
object-storage I/O unless explicitly justified and documented.

## Audited paths (Phase 3)

| Path | Ownership | Notes |
| --- | --- | --- |
| RAG document upload | Service commits DB + outbox; storage compensated on failure | Storage write precedes durable DB row; rollback deletes object |
| RAG document soft-delete | Service commits DB, then queues cleanup worker | Cleanup is async |
| RAG document cleanup worker | DB cleanup commits first; object-storage delete after commit | Storage failure after commit is logged/raised for retry of storage only |
| RAG evaluation `run_dataset` | Creates run row and commits before embed/retrieve loop; commits per case + final status | Prevents embedding HTTP while holding an open write txn |
| Email / external effects | Effect ledger + `run_with_effect_idempotency` | Durable before provider call |
| Project create + Idempotency-Key | Handler runs inside idempotency claim; response stored after success | Framework owns claim lifecycle |

## Explicit exceptions

- Short read-modify-write sequences that only touch the local DB may keep a single
  request-scoped transaction (FastAPI `get_db`).
- Vector chunk deletes during cleanup remain in the DB transaction (same session /
  adapter); only remote object storage is deferred past commit.
