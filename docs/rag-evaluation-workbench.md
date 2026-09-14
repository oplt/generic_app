# RAG evaluation workbench (Phase 11)

Admin/developer UI at `/admin/rag/evaluation` for probing retrieval, managing golden
datasets, running experiments, comparing baselines, and exporting results.

## Capabilities

* Interactive probe: query + project/documents + strategy + top_k
* Per-candidate ranks/scores (vector, lexical, fused, optional reranker)
* Assembled LLM context preview (untrusted-context rules included)
* Datasets / cases with expected chunk/document IDs, facts, tags, judgments
* Runs with Recall@K, Precision@K, MRR, nDCG@K
* Each run stores `configuration_json` including retrieval `strategy`, quality/
  rerank knobs, and the active RAG `index_version` / pipeline snapshot
* Optional heuristic generation judges (groundedness, citation correctness,
  faithfulness, answer relevance) — **no mandatory LLM-as-judge**
* Baseline vs candidate metric deltas
* JSON / CSV export

## Authz and tenancy

* Routes require `rag.manage`
* Datasets and runs are scoped by `organization_id` when provided, otherwise by
  creating `user_id`
* Retrieval always uses the caller's user identity and optional project filters —
  no cross-tenant document access

## API (prefix `/api/v1/rag/admin/evaluation`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/datasets` | List datasets |
| POST | `/datasets` | Create dataset |
| POST | `/datasets/import-golden` | Import offline `golden_v1.json` |
| GET/POST | `/datasets/{id}/cases` | List / create cases |
| POST | `/probe` | Interactive retrieval inspection |
| POST | `/datasets/{id}/runs` | Execute evaluation run |
| GET | `/runs` | List runs |
| GET | `/runs/{id}` | Run detail + items |
| GET | `/runs/{id}/export?format=json\|csv` | Download results |

## Persistence

Migration `k1a8c2d3e049`:

* `rag_evaluation_datasets`
* `rag_evaluation_cases`
* `rag_evaluation_runs`
* `rag_evaluation_run_items`

## Offline harness

The deterministic CLI remains available:

```sh
PYTHONPATH=. uv run --project backend python -m backend.modules.rag.evaluation \
  --json-output /tmp/rag-evaluation.json
```

Shared metrics live in `backend/modules/rag/evaluation/metrics.py`.

## Related

* Hybrid search: [hybrid-search.md](hybrid-search.md)
* Module README: [backend/modules/rag/README.md](../backend/modules/rag/README.md)
* Offline eval README: [backend/modules/rag/evaluation/README.md](../backend/modules/rag/evaluation/README.md)
