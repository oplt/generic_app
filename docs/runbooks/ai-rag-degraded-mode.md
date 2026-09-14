# AI/RAG degraded-mode runbook

## Signals

- `rag_retrieval_degraded_total`: retrieval failed or was explicitly degraded.
- `rag_vector_readiness_failure_total{reason}`: pgvector extension, column, index, dimension,
  readiness-check, or query failure.
- pgvector retrieval no longer falls back to JSON scoring; schema/extension failures increment
  the normal retrieval-degraded metrics and must be repaired before accepting traffic.
- `rag_injection_chunks_filtered_total`: unsafe chunks were excluded.
- `agent_context_degraded_total{source}`: agent retrieval or memory recall degraded.
- `ai_run_failed_total`, `ai_run_latency_ms`, `agent_run_latency_ms`: generation health.
- API responses and `ai_runs`: `retrieval_degraded`, `memory_degraded`,
  `degradation_reason`, `injection_chunks_filtered`.

## Triage

1. Correlate the API request, worker log, and trace using `correlation_id`.
2. Verify the PostgreSQL `vector` extension, HNSW index, embedding dimensions, and that completed
   documents have populated `rag_chunks.embedding`.
   Readiness re-probes failed dependencies after a short cooldown; clear the process readiness
   cache after emergency schema repair if immediate recovery is required.
3. If retrieval reports no matches without degradation, inspect score threshold, document ownership,
   project scope, ingestion status, and query/document filters. Do not lower the threshold globally
   before testing representative queries.
4. If memory degrades, verify Redis and Mem0 mode/configuration. Generation may continue without
   memory; the response flag is the user-visible record of that fallback.
5. If injection filtering rises, inspect the source documents and ingestion metadata. Do not bypass
   the filter to recover recall.

## Recovery

- Re-index affected documents after correcting vector dimensions or parser failures.
- Restore pgvector before accepting retrieval traffic; JSON embedding data is reserved for repair
  and migration tooling.
- Do not enable a JSON similarity scan or alternate vector backend as an operational workaround.
- Retry failed Celery ingestion, cleanup, or memory-extraction jobs after the dependency recovers.
- Confirm recovery by checking degradation counters stop increasing and running a RAG evaluation
  dataset with expected chunk IDs.

## Safe operating rules

- Keep `RAG_VECTOR_BACKEND=pgvector`; unsupported backends fail startup validation.
- Keep strict generation timeouts and per-user/IP rate limits enabled.
- Never log prompt contents, memory contents, API keys, or `.env` values during triage.
