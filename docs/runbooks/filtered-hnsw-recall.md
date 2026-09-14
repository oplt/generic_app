# Filtered HNSW recall measurement

Tenant filters around `ORDER BY embedding <=> query` can make Approximate Nearest Neighbor
(HNSW) return fewer or less relevant rows than an exact distance ranking of the same filtered
set. Tune `hnsw.ef_search`, candidate over-fetch, or `hnsw.iterative_scan` only when
`EXPLAIN (ANALYZE, BUFFERS)` shows the embedding HNSW index on the production query and
Recall@K is below 1.0.

## What the harness measures

Module: `backend.modules.rag.evaluation.filtered_hnsw`

For each filter type (`user`, `organization`, `project`, `document`, `source`) it:

1. Builds a skewed corpus where unfiltered neighbors prefer other tenants.
2. Runs an **exact** filtered ranking (`SET LOCAL enable_indexscan/bitmapscan = off`).
3. Runs the **production** filtered SQL and records the plan class.
4. Runs a **post-filter ANN** probe (unfiltered HNSW over-fetch, then apply filters).
5. Sweeps transaction-local `hnsw.ef_search` and candidate multipliers when supported.
6. Probes `hnsw.iterative_scan` only on pgvector >= 0.7.

All knobs use `SET LOCAL` so pooled connections cannot leak session settings.

## Command

```sh
PYTHONPATH=. uv run --project backend python -m backend.modules.rag.evaluation.filtered_hnsw \
  --noise-chunks 800 --top-k 5 \
  --json-output /tmp/filtered-hnsw-recall.json
```

Optional flags: `--target-relevant`, `--target-filler`, `--postfilter-overfetch`,
`--score-threshold`, `--keep-fixture`.

## Measured baseline (this environment)

Captured 2026-09-14 against:

| Component | Version |
| --- | --- |
| PostgreSQL | 16.15 |
| pgvector | 0.6.2 |
| HNSW index | `ix_rag_chunks_embedding_hnsw` (`vector_cosine_ops`) |
| `hnsw.ef_search` | supported via `SET LOCAL` |
| `hnsw.iterative_scan` | **not** available (requires pgvector >= 0.7) |

Fixture: 800 noise chunks + 5 relevant + 20 filler + chat source rows. Top-K = 5.

| Filter | Production plan | Production Recall@5 | Production latency (ms) | Post-filter ANN Recall@5 |
| --- | --- | ---: | ---: | ---: |
| user | filter_then_sort | 1.0 | ~1.1 | 0.0 |
| organization | filter_then_sort | 1.0 | ~0.9 | 0.0 |
| project | filter_then_sort | 1.0 | ~1.0 | 0.0 |
| document | filter_then_sort | 1.0 | ~1.1 | 0.0 |
| source | filter_then_sort | 1.0 | ~0.8 | 0.0 |

Mean production Recall@5 = **1.0**. Embedding HNSW did not appear in production plans; PostgreSQL
chose tenant btree predicates then sorted by distance. Mean post-filter ANN Recall@5 = **0.0**,
which confirms the skewed corpus would break a naive “ANN then filter” path.

## Chosen settings (from plans, not guesses)

| Setting | Choice | Trade-off |
| --- | --- | --- |
| `hnsw.ef_search` | leave unset (Postgres/pgvector default) | No Recall@K gain while plans are filter-then-sort; raising it only adds work |
| Candidate multiplier for vector SQL | keep current RetrievalService ownership (no extra HNSW-only multiply) | Exact filtered ranking already returns full top-K |
| `hnsw.iterative_scan` | unavailable / do not emulate | Re-evaluate after upgrading pgvector to >= 0.7 if plans switch to HNSW + Filter |

Do **not** `SET` these GUCs at connection checkout. If a future staging run shows
`Index Scan using ix_rag_chunks_embedding_hnsw` with Recall@K < 1.0, apply the harness
recommendation with `SET LOCAL` inside the retrieval transaction only.

## When to re-run

- pgvector or PostgreSQL upgrades
- Large production-like corpus sizes where EXPLAIN starts choosing the embedding HNSW index
- Changes to tenant predicates in `backend/modules/rag/infrastructure/chunk_search.py`
- Before enabling any global `hnsw.*` GUC

## Tests

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --project backend pytest -q \
  backend/modules/rag/tests/test_filtered_hnsw_recall.py

RUN_INTEGRATION_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --project backend pytest -q \
  backend/modules/rag/tests/test_filtered_hnsw_recall.py
```
