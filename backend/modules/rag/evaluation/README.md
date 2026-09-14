# Offline RAG baseline

Online admin workbench (datasets, probe, runs, export): see
[`docs/rag-evaluation-workbench.md`](../../../docs/rag-evaluation-workbench.md)
and UI `/admin/rag/evaluation`.

Run the versioned golden corpus without production data, PostgreSQL, network access, or provider
credentials:

```sh
PYTHONPATH=. uv run --project backend python -m backend.modules.rag.evaluation \
  --json-output /tmp/rag-evaluation.json
```

The command prints a human-readable comparison and writes a machine-readable JSON report. It
compares vector-only retrieval, the current `HybridRetrievalRanker`, independently generated
lexical/vector lanes fused with reciprocal-rank fusion, plus optional Phase 12 quality
variants (`hybrid_exact_dedup`, `hybrid_mmr`). The report contains Recall@K,
Precision@K, MRR, nDCG@K, citation correctness, stage P50/P95/P99 latency, estimated token usage,
and provider cost.

Retrieval metrics and ranked chunk IDs are deterministic. Runtime percentiles are observational
and will vary by host; compare them under the same environment. In the setup timings, `parse`
measures loading the JSON dataset and `chunk` measures materializing its judged chunks. The local
feature-hash embedding and extractive answer make this a reproducible regression baseline, not a
substitute for a production parser, provider, database plan, or representative-user evaluation.

To verify repeatability, run the command twice and compare each strategy's `aggregate`, `cases`,
and the dataset hash while ignoring performance fields. Changes to the corpus are explicit and
reviewable in `golden_v1.json`.

## Filtered HNSW recall (live PostgreSQL)

Measure filtered Recall@K against exact distance search and capture
`EXPLAIN (ANALYZE, BUFFERS)` before changing `hnsw.ef_search` or candidate over-fetch:

```sh
PYTHONPATH=. uv run --project backend python -m backend.modules.rag.evaluation.filtered_hnsw \
  --noise-chunks 800 --top-k 5 \
  --json-output /tmp/filtered-hnsw-recall.json
```

See [`docs/runbooks/filtered-hnsw-recall.md`](../../../docs/runbooks/filtered-hnsw-recall.md) for
the measured baseline and the plan-driven tuning rule (leave `hnsw.ef_search` unset while
production plans remain filter-then-sort).
