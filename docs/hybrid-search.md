# True hybrid search (Phase 10)

RAG retrieval uses **independent** vector and lexical candidate lanes, then
fuses ranks with Reciprocal Rank Fusion (RRF). Lexical hits that ANN never
returned can still enter the final set.

## Strategies

| Strategy | Embedding | Lanes | Fusion |
| --- | --- | --- | --- |
| `vector` | yes | pgvector ANN only | — |
| `lexical` | no | PostgreSQL FTS only | — |
| `hybrid_rrf` | yes | ANN + FTS in parallel | RRF |

Configure defaults with `RAG_RETRIEVAL_STRATEGY`. Override per request on
`POST /api/v1/rag/retrieve` via `strategy`.

Optional `RAG_RERANK_ENABLED` applies a local lexical reranker **after**
candidate generation / fusion. That is separate from lane expansion.

## Candidate expansion (single layer)

All lane sizing goes through
`backend/modules/rag/application/candidate_expansion.py`.

| Setting | Meaning |
| --- | --- |
| `RAG_VECTOR_CANDIDATE_COUNT` | Explicit ANN limit (`0` = derive) |
| `RAG_LEXICAL_CANDIDATE_COUNT` | Explicit FTS limit (`0` = derive) |
| `RAG_RERANK_CANDIDATE_MULTIPLIER` | Used once when deriving limits for hybrid or post-rerank |
| `RAG_RRF_K` | RRF constant `k` in `1 / (k + rank)` |
| `RAG_TOP_K` / request `top_k` | Final result size |

Do not multiply `top_k` again in adapters or SQL callers.

## Tenant and document filters

Both lanes share `_scope_filters` in `chunk_search.py`:

* user / organization isolation
* project filter
* document ID allow-list
* source type
* indexed + non-deleted documents only

## Lexical storage

Migration `j0f7b5d1e148` adds a stored generated column:

```sql
content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED
```

GIN index: `ix_rag_chunks_content_tsv`. The lexical lane queries `content_tsv`
directly instead of recomputing `to_tsvector(...)` per row.

## Query-plan analysis

Run against a migrated database with representative tenant filters. Replace
placeholders with real UUIDs.

### Lexical (expect Bitmap Index Scan on GIN)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.id, ts_rank_cd(c.content_tsv, plainto_tsquery('simple', 'ZX-204')) AS score
FROM rag_chunks c
INNER JOIN rag_documents d ON d.id = c.document_id
WHERE c.user_id = '<user-id>'
  AND d.status = 'indexed'
  AND d.deleted_at IS NULL
  AND c.content_tsv @@ plainto_tsquery('simple', 'ZX-204')
ORDER BY score DESC
LIMIT 15;
```

Healthy signals:

* `Bitmap Index Scan on ix_rag_chunks_content_tsv`
* no sequential scan of `rag_chunks` for the FTS predicate

### Vector (expect HNSW / ANN path)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.id, 1 - (c.embedding <=> CAST('[...]' AS vector)) AS score
FROM rag_chunks c
INNER JOIN rag_documents d ON d.id = c.document_id
WHERE c.user_id = '<user-id>'
  AND d.status = 'indexed'
  AND d.deleted_at IS NULL
  AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> CAST('[...]' AS vector)
LIMIT 15;
```

Healthy signals:

* index scan using `ix_rag_chunks_embedding_hnsw` (or iterative filtered ANN)
* filters applied as documented in
  [filtered-hnsw-recall](runbooks/filtered-hnsw-recall.md)

If FTS plans show expression rewrites without the GIN index, confirm
`content_tsv` exists and migrations are at head.

## Fusion

```text
score(chunk) = Σ 1 / (k + rank_in_lane)
```

Ranks are not raw cosine / `ts_rank_cd` values. RRF avoids mixing incomparable
score scales. Metadata may still carry per-lane scores for debugging.

## Related

* Module overview: [backend/modules/rag/README.md](../backend/modules/rag/README.md)
* Offline eval harness: `backend/modules/rag/evaluation/`
* Index versions: [rag-index-versions.md](rag-index-versions.md)
