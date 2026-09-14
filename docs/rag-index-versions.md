# Versioned RAG indexes

RAG documents and chunks store durable pipeline metadata. An **index version**
lifecycle tracks which configuration is active and which documents are stale.

## Pipeline fields

Stored on document/chunk `metadata_json` via `pipeline_version_metadata()`:

- `parser_version`
- `chunker_version`
- `embedding_schema_version`
- `embedding_provider`
- `embedding_model`
- `embedding_dimensions`
- `index_version` (fingerprint key `idx-…`)

Source: `backend/modules/rag/application/pipeline_versions.py`.

## Index version lifecycle

Table `rag_index_versions` (migration `i9e6a4c0d037`):

```text
building → validated → active → retired
```

- Runtime config auto-creates/activates a matching active version.
- Changing embedding **dimensions** requires an Alembic change to the fixed
  pgvector column (`RAG_VECTOR_DIMENSIONS=1536`) before activation — the API
  rejects incompatible versions instead of destructive schema rewrites.
- Reindex is **non-destructive**: stale documents enqueue existing ingestion
  jobs that replace chunks in place when dimensions match.

## Admin API (`rag.manage`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/rag/admin/index-status` | Active version, counts, jobs |
| GET | `/api/v1/rag/admin/index-versions` | List versions |
| POST | `/api/v1/rag/admin/index-versions` | Snapshot building version |
| POST | `/api/v1/rag/admin/index-versions/{id}/validate` | Mark validated |
| POST | `/api/v1/rag/admin/index-versions/{id}/activate` | Activate (retire previous) |
| POST | `/api/v1/rag/admin/reindex-stale` | Enqueue stale reindex jobs |

## Admin UI

Settings → **RAG Indexes** (`/admin/rag-indexes`).

## Stale detection

`document_needs_reindex()` compares full pipeline metadata (not only embedding
model). Document list responses set `needs_reindex` accordingly.
