# Phase 7 acceptance baselines

Measured values only. Do **not** invent performance targets. Re-run the listed commands
when comparing before/after changes.

## Profile matrix (7.1)

Automated in:

* `backend/modules/platform/tests/test_capability_profiles.py`
* `scripts/phase7-acceptance.sh`

Each of `core`, `lean_saas`, `rag`, `agent`, `automation_suite`, `client_portal`,
`full_platform` must differ on routers, Celery queues, and frontend page keys.
Default runtime profile remains `full_platform`.

## Generator smoke (7.2)

`orders` with CRUD + frontend + permissions + Celery + events is covered by golden
fixtures and marker-wiring tests under `backend/tools/generic_app/tests` (no manual
router/nav/Celery/Alembic parent edits). Reproduce:

```bash
./scripts/generic-app create-module --help
UV_CACHE_DIR=/tmp/generic-app-uv PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  uv run --project backend pytest -q backend/tools/generic_app/tests
```

## RAG blue/green + isolation (7.3)

Service/unit acceptance:

* `backend/tests/test_phase7_acceptance.py` — activate gates, rollback, tenant+index filters
* `backend/modules/rag/tests/test_index_versions.py` — lifecycle edges
* `backend/modules/rag/tests/test_hybrid_search.py` / `test_retrieval.py` — vector/lexical/hybrid

Manual operator path (staging with MinIO + worker): upload → index → probe strategies →
create candidate → reindex → validate → activate → query → rollback → delete. Tenant
isolation is enforced by `_scope_filters` (`user_id` / `organization_id` / `index_version_id`).

## Failure injection (7.4)

Catalog: `backend/lib/failure_injection/kinds.py`  
Suite: `backend/tests/test_failure_injection_resilience.py` (+ Phase 7 embedding partial)

Covered in CI: Redis unavailable/timeout/miss-storm, Postgres readiness, AI timeout/429,
storage upload, Celery worker failure + duplicate publish, RAG embedding failure,
pgvector unavailable, email SMTP, production guard, idempotency helpers.

## Load / capacity (7.5)

| Signal | Where measured | Notes |
| --- | --- | --- |
| Frontend bundle P50-style budgets | `frontend/budgets.json` (`measuredAt: 2026-09-14`) | `npm run check:budgets` after `npm run build` |
| DB pool checkout latency P50/P95/P99 | `docs/database-pool-capacity.md` | Run `backend.scripts.db_pool_benchmark`; do not fabricate |
| Filtered HNSW Recall@5 + latency | `docs/runbooks/filtered-hnsw-recall.md` | Mean Recall@5 = 1.0; ~1 ms class latency on fixture |
| Redis / RAG vector / lexical / embed / worker | Prometheus `/metrics` + Grafana | Capture in staging under real load |

Only keep optimizations that improve a measured bottleneck.
