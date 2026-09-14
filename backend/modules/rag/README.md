"""Architecture and setup for the RAG module."""

# RAG Module (LangChain)

Document upload, parsing, chunking, embedding, retrieval, and cited answers — integrated with the existing AI agent and memory layers.

## Architecture

```text
backend/modules/rag/
  domain/           # ParsedDocument, DocumentChunk, RagAnswer, enums
  application/      # ingestion, retrieval, answer, prompt context, legacy AI docs
  infrastructure/   # LangChain splitters/loaders, vector store, repos
  api/              # /api/v1/rag routes
```

Application services include:

- `legacy_ai_document_service.py` — backs `/api/v1/ai/documents*` when RAG is enabled
- `prompt_context_service.py` — shared bounded RAG + memory context for all generation paths
- `rag_tool.py` — low-level agent retrieval helper

LangChain is used **only** in `infrastructure/` (`langchain_text_splitters`, optional `langchain_community` loaders). PDF/DOCX/CSV parsing and text splitting run via `asyncio.to_thread` so the API event loop stays responsive during indexing.

## Context order (agent + memory + RAG)

1. System/developer prompt
2. Authenticated user identity (JWT — never from message text)
3. User/project memory (`MemoryService`)
4. RAG document chunks (`PromptContextService` → `RetrievalService`)
5. Session/working context
6. User question

## Configuration

```env
RAG_ENABLED=true
RAG_VECTOR_BACKEND=pgvector    # pgvector only
RAG_EMBEDDING_PROVIDER=local   # uses existing AiProviderRegistry
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=150
RAG_TOP_K=5
RAG_SCORE_THRESHOLD=0.3
RAG_RETRIEVAL_STRATEGY=hybrid_rrf
RAG_VECTOR_CANDIDATE_COUNT=0
RAG_LEXICAL_CANDIDATE_COUNT=0
RAG_RRF_K=60
RAG_MAX_CONTEXT_TOKENS=6000
RAG_RERANK_ENABLED=true
RAG_RERANK_CANDIDATE_MULTIPLIER=3
RAG_RERANKER_BACKEND=lightweight
# Quality strategies default off — see docs/rag-quality.md
RAG_DOCUMENT_AWARE_CHUNKING=false
RAG_PARENT_CHILD_CHUNKING=false
RAG_DEDUP_EXACT=false
RAG_MMR_ENABLED=false
RAG_NEIGHBOR_EXPANSION=false
RAG_ALLOWED_FILE_TYPES=pdf,txt,md,docx,csv
RAG_MAX_FILE_BYTES=10485760
```

Embeddings use the same provider registry as `/api/v1/ai` — no hardcoded API keys.
Quality options (parent/child, dedup, MMR, neighbors, embedding batching) are documented in
[`docs/rag-quality.md`](../../../docs/rag-quality.md); defaults stay off until measured.

## Vector backend

| Backend | Status |
|---------|--------|
| `pgvector` | Required production backend — `rag_chunks.embedding` column with HNSW cosine index; SQL `ORDER BY embedding <=> query` |
| JSON embedding data | Retained only for migration/repair tooling; never read by request-path retrieval |

The schema is fixed at 1536 dimensions. The application rejects another dimension value while
pgvector is enabled; change the schema through a deliberate migration before changing models.
Retrieval requires the `vector` extension, `rag_chunks.embedding`, and the cosine HNSW index.
Tune filtered ANN (`hnsw.ef_search`, iterative scan) only from the measured runbook
[`docs/runbooks/filtered-hnsw-recall.md`](../../../docs/runbooks/filtered-hnsw-recall.md).
When `RAG_RETRIEVAL_STRATEGY=hybrid_rrf` (default), retrieval runs independent
pgvector ANN and PostgreSQL FTS lanes (`content_tsv` / `ix_rag_chunks_content_tsv`),
fuses them with configurable RRF (`RAG_RRF_K`), then optionally applies the local
hybrid reranker when `RAG_RERANK_ENABLED=true`. Candidate expansion happens in one
place (`candidate_expansion.py`); set `RAG_VECTOR_CANDIDATE_COUNT` /
`RAG_LEXICAL_CANDIDATE_COUNT` or derive once via `RAG_RERANK_CANDIDATE_MULTIPLIER`.
Lexical-lane failures fall back to vector-only candidates. Missing readiness
fails closed and returns degraded retrieval; it never scans `embedding_json`.
See [docs/hybrid-search.md](../../../docs/hybrid-search.md) for strategies and
EXPLAIN guidance.

## AI document route consolidation

When `RAG_ENABLED=true` (default), legacy `/api/v1/ai/documents*` routes are served by `LegacyAiDocumentService` in this module (invoked from `AiService` / `ai/router.py`):

| AI route | Backing |
|----------|---------|
| `GET /ai/documents` | `rag_documents` |
| `POST /ai/documents` | upload + async index |
| `POST /ai/documents/upload` | upload + async index |
| `POST /ai/retrieve` | pgvector retrieval via `RetrievalService` |

The frontend can keep using `/ai/documents`; documents land in one corpus. Set `RAG_EMBEDDING_PROVIDER` empty to inherit `AI_EMBEDDING_PROVIDER`.

After deploy, run:

```sh
cd backend && alembic upgrade head
```

Migration `c4e8f2a91d03` enables the `vector` extension, adds the `embedding vector(1536)` column,
creates `ix_rag_chunks_embedding_hnsw`, and adds tenant/filter indexes. Verify the live schema
before enabling production retrieval.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/rag/documents/upload` | Upload + queue indexing (returns job) |
| GET | `/api/v1/rag/documents` | List documents |
| GET | `/api/v1/rag/documents/{id}` | Get document |
| DELETE | `/api/v1/rag/documents/{id}` | Soft delete |
| POST | `/api/v1/rag/documents/{id}/index` | Queue re-index (202 + job) |
| GET | `/api/v1/rag/documents/{id}/chunks` | List chunks |
| POST | `/api/v1/rag/retrieve` | Similarity search |
| POST | `/api/v1/rag/ask` | RAG answer with citations |
| GET | `/api/v1/rag/queries` | Query history |
| GET | `/api/v1/rag/jobs/{id}` | Ingestion job status |
| POST | `/api/v1/rag/jobs/{id}/retry` | Repair/retry ingestion via a fresh outbox event |
| * | `/api/v1/rag/admin/evaluation/*` | Evaluation workbench (requires `rag.manage`) — see [docs/rag-evaluation-workbench.md](../../../docs/rag-evaluation-workbench.md) |

## Upload and index

All parsing, chunking, and embedding runs in the background via `index_rag_document_task` — HTTP handlers only persist the file and enqueue work.

```bash
curl -X POST http://localhost:8000/api/v1/rag/documents/upload \
  -H "Cookie: access_token=..." \
  -F "file=@notes.md" \
  -F "project_id=<optional-uuid>"
```

Response includes `document` and `ingestion_job`. Poll `GET /api/v1/rag/jobs/{id}` for status.

Re-index an existing document:

```bash
curl -X POST http://localhost:8000/api/v1/rag/documents/{document_id}/index \
  -H "Cookie: access_token=..."
```

Returns `202 Accepted` with a pending job.

Repair a failed or stuck job without mutating the original history:

```bash
curl -X POST http://localhost:8000/api/v1/rag/jobs/{job_id}/retry \
  -H "Cookie: access_token=..."
```

For local development, `CELERY_TASK_ALWAYS_EAGER=true` may run indexing in a daemon background
thread inside the API process. Production configuration rejects eager mode; use real Celery
workers (`CELERY_TASK_ALWAYS_EAGER=false`) so embedding work does not consume API resources.

## Ask

```json
POST /api/v1/rag/ask
{
  "query": "What database did we choose?",
  "project_id": "<optional>"
}
```

Returns `answer`, `citations[]`, `no_context_found` when nothing matches, and `ai_run_id` linking to the `ai_runs` record (cost/tokens/review parity with `/ai/runs`). `citation_validated=false` and `needs_review=true` identify answers whose source references or claim grounding could not be verified.

The request is bounded by `RAG_ASK_TIMEOUT_SECONDS`. Degradation fields identify retrieval or
memory failures, and `injection_chunks_filtered` reports excluded unsafe chunks. See
[`docs/runbooks/ai-rag-degraded-mode.md`](../../../docs/runbooks/ai-rag-degraded-mode.md).

Generation goes through `GenerationPort` (`backend/lib/generation_port.py`, adapter: `AiServiceGenerationPort`) using the prompt template keyed by `RAG_ASK_PROMPT_TEMPLATE_KEY` (default `rag-answer`), with built-in defaults when that template is absent.

## Agent integration

`AgentService` calls the same `PromptContextService` as `/rag/ask` and `/ai/runs` when
`RAG_ENABLED=true`.

## Access control

- Documents scoped by `user_id` and optional `organization_id` / `project_id`
- When `project_id` is set, `organization_id` must be that project's organization
  (see ADR 0004); `ProjectAccessPort.resolve_ownership_scope` derives the pair
- `project_id` requires project membership (`ProjectAccessPort.ensure_project_access`)
- Organization-scoped chunks are visible to other members with the same `organization_id`
- Retrieval cache keys include a user-independent corpus generation; upload/reindex/delete and
  project assignment changes bump it so no member keeps a stale shared entry
- Call `invalidate_retrieval_cache_for_organization` after membership/permission revokes
- Pipeline metadata stores `parser_version`, `chunker_version`, `embedding_schema_version`,
  embedding provider/model/dimensions, and `index_version` for stale-document detection
- Index version lifecycle + admin status: see [docs/rag-index-versions.md](../../../docs/rag-index-versions.md)
- Admins can delete/index only when `is_admin` checks pass

## Prompt injection safety

Retrieved chunks are wrapped with untrusted-context rules. Document instructions cannot override system safety policies.

## Setup

```sh
cd backend
uv sync
alembic upgrade head
```

## Tests

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --project backend pytest -q backend/modules/rag/tests
```

## Offline evaluation baseline

Run the versioned local golden corpus and emit a human summary plus JSON report:

```sh
PYTHONPATH=. uv run --project backend python -m backend.modules.rag.evaluation \
  --json-output /tmp/rag-evaluation.json
```

See [`evaluation/README.md`](evaluation/README.md) for metric definitions and limitations.

## Vector backend

Only `pgvector` is supported. The app fails fast at startup if `RAG_VECTOR_BACKEND` is set to an unsupported value. External vector DBs (e.g. Qdrant) require a new adapter implementation before enabling a new backend name in config.
