# Cross-feature integration

This page maps cross-feature wiring in this repo. Use it with the living roadmap
in `tasks.txt` (gap-closure phases). The audit brief lives in `prompt.txt`.
Acceptance baselines: [acceptance-baselines.md](acceptance-baselines.md).

| Integration | Status | Where |
| --- | --- | --- |
| Module generator → manifests | Done | `backend/tools/generic_app/` markers → registry/router_registry/celery/FE |
| Manifests → capability profiles | Done | `resolve_active_modules` gates routers/Celery/frontend allow-lists |
| RBAC → manifests | Done | `ModuleManifest.required_permissions` + policy catalog |
| Cache → RBAC | Done | `PolicyService` + `app_cache` tags/invalidation |
| Jobs console → Celery | Done | `/admin/jobs` aggregates `application_jobs` + RAG jobs |
| Diagnostics → observability | Done | `/admin/diagnostics` hints include Grafana/Tempo URLs |
| RAG versioning → jobs | Done | Side-by-side chunk lanes + reindex/validate/activate/rollback |
| Evaluation → index versions | Done | Run `configuration_json.index_version` + pipeline snapshot |
| Evaluation → hybrid strategies | Done | `vector` / `lexical` / `hybrid_rrf` (+ rerank/quality knobs) |
| Failure injection → diagnostics | Done | Active faults listed under observability hints; probes degrade |
| Frontend → OpenAPI | Done | Priority admin APIs wrap Orval clients; `rawApiPathGuard` |
| Profiles → FE lazy routes | Done | `ModuleRouteGate` + platform `module_routes` |

## Acceptance checklist (developer path)

1. `uv run --project backend python -m backend.tools.generic_app create-module …`
2. Enable via platform module pack / capability profile
3. `npm run api:generate` for typed frontend client
4. Protect routes with `require_permission(...)` / UI admin gates / `ModuleRouteGate`
5. Use `app_cache` / `cache_get_json` — no module-private Redis clients
6. Use idempotency helpers for unsafe retries
7. Use `bounded_gather` / provider concurrency helpers
8. Inspect `/admin/jobs`
9. Inspect `/admin/diagnostics`
10. Enable `DEVELOPER_DIAGNOSTICS_ENABLED` for the local request panel
11. Use `injecting(...)` / `FAILURE_INJECTION_ENABLED` (never in production)
12–15. RAG index versions, hybrid retrieve, evaluation workbench, metric compare

## Phase 7 harness

```bash
./scripts/phase7-acceptance.sh
```

Also:

```bash
UV_CACHE_DIR=/tmp/generic-app-uv PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  uv run --project backend pytest -q \
  backend/tests/test_cross_feature_integration.py \
  backend/tests/test_phase7_acceptance.py \
  backend/modules/manifests/tests \
  backend/modules/platform/tests/test_capability_profiles.py \
  backend/modules/policy/tests \
  backend/modules/jobs/tests \
  backend/modules/diagnostics/tests \
  backend/tests/test_failure_injection_resilience.py
```
