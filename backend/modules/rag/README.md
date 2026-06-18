"""Architecture and setup for the RAG module."""

# RAG Module (LangChain)

Document upload, parsing, chunking, embedding, retrieval, and cited answers — integrated with the existing AI agent and memory layers.

## Architecture

```text
backend/modules/rag/
  domain/           # ParsedDocument, DocumentChunk, RagAnswer, enums
  application/      # ingestion, retrieval, answer, citations (no LangChain imports)
  infrastructure/   # LangChain splitters/loaders, vector store, repos
  api/              # /api/v1/rag routes
```

LangChain is used **only** in `infrastructure/` (`langchain_text_splitters`, optional `langchain_community` loaders).

## Context order (agent + memory + RAG)

1. System/developer prompt
2. Authenticated user identity (JWT — never from message text)
3. User/project memory (`MemoryService`)
4. RAG document chunks (`rag_search_tool`)
5. Session/working context
6. User question

## Configuration

```env
RAG_ENABLED=true
RAG_VECTOR_BACKEND=pgvector    # pgvector | qdrant
RAG_EMBEDDING_PROVIDER=local   # uses existing AiProviderRegistry
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=150
RAG_TOP_K=5
RAG_SCORE_THRESHOLD=0.3
RAG_MAX_CONTEXT_TOKENS=6000
RAG_ALLOWED_FILE_TYPES=pdf,txt,md,docx,csv
RAG_MAX_FILE_BYTES=10485760
```

Embeddings use the same provider registry as `/api/v1/ai` — no hardcoded API keys.

## Vector backend

| Backend | Status |
|---------|--------|
| `pgvector` | Default — embeddings in `rag_chunks.embedding_json`, filtered cosine search in Postgres |
| `qdrant` | Adapter stub for future external DB |

Native pgvector columns can be added later without changing application services.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/rag/documents/upload` | Upload + queue indexing |
| GET | `/api/v1/rag/documents` | List documents |
| GET | `/api/v1/rag/documents/{id}` | Get document |
| DELETE | `/api/v1/rag/documents/{id}` | Soft delete |
| POST | `/api/v1/rag/documents/{id}/index` | Manual re-index |
| GET | `/api/v1/rag/documents/{id}/chunks` | List chunks |
| POST | `/api/v1/rag/retrieve` | Similarity search |
| POST | `/api/v1/rag/ask` | RAG answer with citations |
| GET | `/api/v1/rag/queries` | Query history |
| GET | `/api/v1/rag/jobs/{id}` | Ingestion job status |

## Upload and index

```bash
curl -X POST http://localhost:8000/api/v1/rag/documents/upload \
  -H "Cookie: access_token=..." \
  -F "file=@notes.md" \
  -F "project_id=<optional-uuid>"
```

With `CELERY_TASK_ALWAYS_EAGER=true` (dev), indexing runs inline after upload.

## Ask

```json
POST /api/v1/rag/ask
{
  "query": "What database did we choose?",
  "project_id": "<optional>"
}
```

Returns `answer`, `citations[]`, `no_context_found` when nothing matches.

## Agent integration

`AgentService` calls `rag_search_tool()` before LLM generation when `RAG_ENABLED=true`. Same tool is available for future explicit agent tool loops.

## Access control

- Documents scoped by `user_id`
- `project_id` requires project membership (`ProjectsRepository.get_by_id_for_user`)
- Retrieval never returns another user's chunks
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
PYTHONPATH=. uv run --project backend python -m unittest discover -s backend/modules/rag/tests -v
```

## Switching vector backend

Set `RAG_VECTOR_BACKEND=qdrant` and implement/configure Qdrant in `infrastructure/qdrant_adapter.py` when ready.
