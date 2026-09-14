# Versioned RAG indexes (blue/green)

RAG documents and chunks store durable pipeline metadata. An **index version**
lifecycle tracks which configuration is active and which documents are built
per version.

## Pipeline fields

Stored on document/chunk `metadata_json` via `pipeline_version_metadata()`:

- `parser_version`
- `chunker_version`
- `embedding_schema_version`
- `embedding_provider`
- `embedding_model`
- `embedding_dimensions`
- `index_version` (fingerprint key `idx-…`)

Relational source of truth for retrieval:

- `rag_chunks.index_version_id` → `rag_index_versions.id`

Source: `backend/modules/rag/application/pipeline_versions.py`.

## Index version lifecycle

Table `rag_index_versions` (migrations `i9e6a4c0d037`, `n4d1f6a7b372`):

```text
building → validated → active → retired
```

Rules:

- Runtime config drift **does not** auto-activate a new version. The previous
  active version keeps serving; a **building** candidate is opened for the
  desired fingerprint.
- Cold start (empty catalog) bootstraps a validated+active version once.
- `building → active` is forbidden. Validate first.
- Activation requires promotion readiness (dimensions, coverage, failed jobs,
  chunk presence, no active ingest jobs).
- PostgreSQL partial unique index `uq_rag_index_versions_one_active` enforces
  at most one `status = 'active'`.
- Rollback re-activates a **retired** version without re-embedding (chunks kept
  until retention cleanup).

Changing embedding **dimensions** still requires an Alembic change to the fixed
pgvector column (`RAG_VECTOR_DIMENSIONS=1536`) before activation.

## Side-by-side build

Indexing writes chunks for the **write target** (desired building/validated, else
active). `replace_chunks` deletes only `(document_id, index_version_id)` rows,
so V1 chunks remain while V2 builds.

Retrieval constrains both vector and lexical lanes with:

```text
c.index_version_id = :active_index_version_id
```

Cache variants include the active version id.

## Retention

`RAG_INDEX_RETENTION_DAYS` (default 14). Beat task
`cleanup_retired_rag_index_versions_task` deletes chunks for retired versions
past retention.

Promotion knobs:

- `RAG_INDEX_ACTIVATION_MIN_DOC_COVERAGE` (default `0.95`)
- `RAG_INDEX_ACTIVATION_MAX_FAILED_JOBS` (default `0`)

## Admin API (`rag.manage`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/rag/admin/index-status` | Active/desired/building, incomplete counts |
| GET | `/api/v1/rag/admin/index-versions` | List versions |
| POST | `/api/v1/rag/admin/index-versions` | Snapshot building version |
| POST | `/api/v1/rag/admin/index-versions/{id}/validate` | Mark validated |
| POST | `/api/v1/rag/admin/index-versions/{id}/activate` | Activate (retire previous) |
| POST | `/api/v1/rag/admin/index-versions/{id}/rollback` | Rollback to retired |
| POST | `/api/v1/rag/admin/reindex-stale` | Enqueue missing builds for write target |

## Admin UI

Settings → **RAG Indexes** (`/admin/rag-indexes`).
