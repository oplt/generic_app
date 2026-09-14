# ADR 0003: Modular capability boundaries and durable jobs

Status: accepted

## Decision

Keep the modular monolith. Capability services own business workflows; thin
facades coordinate them for compatibility with existing imports. AI review and
provider capabilities are composed by `AiService`; platform capabilities are
composed by `PlatformService`.

RAG context construction receives retrieval, memory, and configuration through
an explicit request context. It does not mutate shared service state per request.

All Celery task families create an `application_jobs` lifecycle record. The
record stores only safe field metadata, correlation ID, attempts, deadlines,
timestamps, retryability, and terminal error state. Raw prompts, email bodies,
tokens, and document content are never persisted in the job payload.

Legacy `ai_documents` mappings live in `ai.legacy_models`, are marked
`legacy_read_only`, and remain registered only for migration metadata. New
document reads/writes belong to RAG.

## Consequences

- Existing facade imports remain valid while method-resolution ambiguity is removed.
- Worker failures are queryable and correlate with logs without exposing secrets.
- Rolling deployments can run additive migrations before code uses new job state.
- The migration CI job runs both `alembic upgrade head` and `alembic check`.
- Infrastructure and secret config writes are blocked in production; deployment
  configuration must be managed outside the application UI.

## Alternatives rejected

- Splitting into microservices: unnecessary operational cost for this monolith.
- Reusing Redis/Celery result state as the source of truth: results expire and
  do not provide durable retry/dead-letter history.
- Deleting legacy tables immediately: unsafe until documented data migration
  and production verification are complete.
