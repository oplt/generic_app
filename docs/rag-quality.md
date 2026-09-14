# RAG quality improvements (Phase 12)

Configurable retrieval/indexing quality strategies. **Defaults preserve the
current production behavior**; enable options only after measuring a win in the
[evaluation workbench](rag-evaluation-workbench.md) or offline harness.

## Defaults (unchanged)

| Area | Default |
| --- | --- |
| Document-aware separators | off (`RAG_DOCUMENT_AWARE_CHUNKING=false`) |
| Parent/child chunking | off |
| Exact / near dedup | off |
| Per-document limit | off (`0`) |
| MMR diversity | off |
| Neighbor expansion | off |
| Reranker | lightweight local (existing) when `RAG_RERANK_ENABLED=true` |
| Expensive rerankers | registered, not default |

Chunk metadata always records `section_path` (when present), `prev_chunk_index`,
`next_chunk_index`, and `chunk_token_count`. Chunker version is `chunker-v2`;
pipeline metadata includes `chunking_mode` (`basic` / `document_aware` /
`parent_child`) for stale detection.

## Config knobs

```env
RAG_DOCUMENT_AWARE_CHUNKING=false
RAG_PARENT_CHILD_CHUNKING=false
RAG_PARENT_CHILD_CHILD_SIZE=200
RAG_PARENT_CHILD_CHILD_OVERLAP=40
RAG_PARENT_CHILD_RETRIEVAL=false
RAG_DEDUP_EXACT=false
RAG_DEDUP_NEAR=false
RAG_DEDUP_NEAR_THRESHOLD=0.9
RAG_PER_DOCUMENT_LIMIT=0
RAG_MMR_ENABLED=false
RAG_MMR_LAMBDA=0.7
RAG_NEIGHBOR_EXPANSION=false
RAG_NEIGHBOR_WINDOW=1
RAG_RERANKER_BACKEND=lightweight   # none|lightweight|cross_encoder|provider|llm
RAG_EMBEDDING_BATCH_SIZE=64
RAG_EMBEDDING_CONCURRENCY=1
RAG_EMBEDDING_MAX_RETRIES=2
RAG_EMBEDDING_ALLOW_PARTIAL_FAILURE=false
```

## Benchmarking

Offline harness strategies (in addition to existing baselines):

* `hybrid_exact_dedup`
* `hybrid_mmr`

```sh
PYTHONPATH=. uv run --project backend python -m backend.modules.rag.evaluation \
  --json-output /tmp/rag-quality-eval.json
```

Workbench runs persist the active quality flags under `configuration.quality`.

## Evaluation note (Phase 12 acceptance)

No quality flag is flipped on by default. Measured offline golden diffs for the
new optional strategies are recorded in `tasks.txt` under P12-001; promote a
strategy to default only after a clear workbench/harness win on representative
tenant data.

## Code map

* `application/quality_strategies.py` — dedup / MMR / parent expand / neighbor merge
* `application/rerankers.py` — pluggable reranker factory
* `application/chunking_service.py` — document-aware + parent/child options
* `application/embedding_service.py` — batch size, concurrency, retries, partial failure
* `application/retrieval_service.py` — applies quality after fusion/rerank

Migration: none (metadata stays in `metadata_json`).
