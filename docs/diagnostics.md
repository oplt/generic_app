# Infrastructure diagnostics (Phase 14)

Admin UI: `/admin/diagnostics`  
API: `GET /api/v1/admin/diagnostics`

Permission: `diagnostics.read` (system admin + org admin).

## What it covers

| Section | Signals |
| --- | --- |
| Application | version, commit, uptime, env, enabled modules |
| PostgreSQL | connectivity, pool usage/limits, migration revision, pgvector |
| Redis | connectivity, latency, memory summary, cache hit ratio, broker host |
| Celery | workers, queues, queue depth, failed jobs, stale workers |
| Object storage | configured + bucket reachability |
| AI providers | configured/missing only — **no paid API calls** |
| RAG | active index version, stale docs, ingestion failures, latency averages from Prometheus |

## Safety rules

* No credentials, DSNs, API keys, or secret payloads
* Hostnames only (credentials stripped via URL redaction)
* Reuses existing health probes + Prometheus gauges/histograms
* Prefer Grafana/Tempo for deep traces (see Observability page)
* Active failure-injection faults (when permitted) appear under `observability_hints.failure_injection`

## Related

* [dependency-degradation.md](runbooks/dependency-degradation.md)
* [database-pool-capacity.md](database-pool-capacity.md)
* Observability UI: `/observability`
* Per-request developer panel: [developer-diagnostics.md](developer-diagnostics.md)
