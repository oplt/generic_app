# Cross-feature integration (Phase 17)

This page maps the prompt’s integration examples to the concrete wiring in this
repo. Use it with the final acceptance checklist in `prompt.txt`.

| Integration | Status | Where |
| --- | --- | --- |
| Module generator → manifests | Done | `backend/tools/generic_app/` + registry wiring |
| Manifests → capability profiles | Done | `backend/modules/platform/profiles.py` |
| RBAC → manifests | Done | `ModuleManifest.required_permissions` + policy catalog |
| Cache → RBAC | Done | `PolicyService` + `app_cache` tags/invalidation |
| Jobs console → Celery | Done | `/admin/jobs` aggregates `application_jobs` + RAG jobs |
| Diagnostics → observability | Done | `/admin/diagnostics` hints include Grafana/Tempo URLs |
| RAG versioning → jobs | Done | Reindex / ingestion appear as `rag-indexing` jobs |
| Evaluation → index versions | Done | Run `configuration_json.index_version` + pipeline snapshot |
| Evaluation → hybrid strategies | Done | `vector` / `lexical` / `hybrid_rrf` (+ rerank/quality knobs) |
| Failure injection → diagnostics | Done | Active faults listed under observability hints; probes degrade |

## Acceptance checklist (developer path)

1. `uv run --project backend python -m backend.tools.generic_app create-module …`
2. Enable via platform module pack / capability profile
3. `npm run api:generate` for typed frontend client
4. Protect routes with `require_permission(...)` / UI admin gates
5. Use `app_cache` / `cache_get_json` — no module-private Redis clients
6. Use idempotency helpers for unsafe retries
7. Use `bounded_gather` / provider concurrency helpers
8. Inspect `/admin/jobs`
9. Inspect `/admin/diagnostics`
10. Enable `DEVELOPER_DIAGNOSTICS_ENABLED` for the local request panel
11. Use `injecting(...)` / `FAILURE_INJECTION_ENABLED` (never in production)
12–15. RAG index versions, hybrid retrieve, evaluation workbench, metric compare

## Tests

```bash
UV_CACHE_DIR=/tmp/generic-app-uv PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  uv run --project backend pytest -q \
  backend/tests/test_cross_feature_integration.py \
  backend/modules/manifests/tests \
  backend/modules/platform/tests/test_capability_profiles.py \
  backend/modules/policy/tests \
  backend/modules/jobs/tests \
  backend/modules/diagnostics/tests \
  backend/tests/test_failure_injection_resilience.py
```
