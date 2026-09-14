# Transaction ownership

Each write use case has one component responsible for its commit. Repositories
only add, update, delete, flush, and query rows; they never commit. A failed
request or worker stage rolls back before the session is returned to the pool.

## Owners

| Use-case boundary | Owner | Commit rule |
| --- | --- | --- |
| API routes that mutate directly (`admin`, `users`, `notifications`, `settings`, and platform configuration routes) | Route | Commit after the complete route-level mutation, including its audit row. |
| API routes delegating to application/domain services (`projects`, `chat`, `profile`, `calendar`, `identity_access`, `rag`, `ai`, and `memory`) | Called service | The route passes the request session and does not commit separately. |
| Application workers (`job_service`) | Worker stage | Each job-state transition is one short transaction; failures explicitly roll back. |
| Outbox dispatcher | Dispatcher invocation | Claim/update and dispatch status are committed once per invocation; failures roll back the batch. |
| RAG indexing | `DocumentIngestionService` stage | Intentional saga: validation state, external parsing/embedding, and final persistence are separate transactions. This is documented and tested rather than treated as one long transaction. |

The API database dependency owns session lifetime and rollback-on-exception; it
does not commit implicitly. This prevents a failed route from returning an
aborted session to the pool while preserving the explicit owner for each write.

When composing a new use case, choose one owner from the table before adding a
write. Do not add a route-level commit around a service that already owns the
mutation. If an external call must occur between durable states, name each stage
and commit boundary explicitly, as RAG indexing does.
