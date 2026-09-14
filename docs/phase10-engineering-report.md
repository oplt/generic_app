# Phase 10 — Engineering report

Final cleanup and validation for the Phases 0–10 architecture pass on `generic_app`.

## CI failures

| Failure | Root cause | Fix |
| --- | --- | --- |
| OpenAPI export needing live PG/Redis/MinIO | Settings constructed from empty CI env | `backend/core/openapi_export.py` + `Settings.for_openapi_export()`; CI uses exporter before Orval |
| MinIO CI flakiness | Unpinned / flaky image | Quay-pinned MinIO in `backend-integration.yml` + compose |
| Frontend audit / lock drift | Transitive vulns | Overrides + documented residuals in `docs/dependency-security.md` |
| Config drift risk (regression) | New required Settings without examples/export | `backend/tests/test_config_contract.py` (Settings ↔ `.env.example` ↔ `OPENAPI_EXPORT_ENV`) |
| ESLint on `pageRegistry` / diagnostics | `any` + react-refresh export rule | Typed lazy loader with targeted eslint exception; move `diagnosticsStateColor` to own module |
| Unit tests env-sensitive | Retrieval requires active index; OTEL exporter `none` | Patch active index in cache test; patch `load_config` in OTEL idempotency test |

## Bugs

| Bug | Location | Notes |
| --- | --- | --- |
| Lazy page views without `default` export would fail `React.lazy` | Module generator `ListView.tsx.j2` | Fixed in Phase 9 (`export default`) |
| E2E shell mocks used `/auth/sign-out` and wrapped `/auth/me` | `architecture-smoke.spec.ts` | Fixed: `/auth/logout`, raw AuthUser body, mock `/profile` |
| Retrieval cache unit test assumed cache path without active index | `test_retrieval_cache.py` | Fixed: mock `_active_index_version_id` |
| OTEL idempotency test assumed traces enabled | `test_runtime_observability.py` | Fixed: patch `load_config` |

## Architecture

### Before

- Feature HTTP mixed with `backend/api/v1/*` stubs; `v1` looked like the product API surface
- Frontend pages often re-exported through `src/pages/*`
- Module visibility inferred from empty route tuples
- OpenAPI export coupled to local infra secrets
- Capability packs existed, but FE gating / surfaces / docs were uneven

### After

- **HTTP ownership:** `backend/modules/<key>/` routers → `router_registry.py` + manifests; `backend/api/v1/` is **health-only**
- **FE ownership:** `features/*/views` + `pageKeys.json` / `pageRegistry.ts`; `ModuleRouteGate` + admin `ProtectedRoute`
- **Surfaces:** explicit `ModuleSurface` (`user_facing` / `admin_facing` / `embedded` / `api_only` / `internal`)
- **Profiles:** named slices (`core`, `rag`, `agent`, …) drive active modules, queues, health checks
- **Contracts:** OpenAPI → Orval SDK + `api:contract:check`; config contract for Settings/examples/export
- **Scaffold:** `generic-app create-module` wires markers; anti-legacy generator tests

## Deleted code

| Deleted | Proof unused / why safe |
| --- | --- |
| `backend/api/v1/{auth,projects,users,workspaces,router}.py` | Empty stubs; real routers live under modules; health retained |
| `frontend/src/pages/**` re-exports | Router imports feature views directly; registry is allow-list |
| `.understand-anything/**` | Local knowledge-graph cache/artifacts; not runtime; safe to drop from tree |

Empty package `__init__.py` files were **not** deleted (intentional packages).

## Incomplete features

| Capability | Status |
| --- | --- |
| Policy / memory / storage / developer diagnostics | Completed as **embedded** or compact admin UX (Phase 3) — not full CRUD apps |
| Orphan OpenAPI ops (~29) | Informational; intentional api-only allow-list for headless |
| Hand-written `src/api/*` Class C wrappers | Prefer Orval; migrate opportunistically |
| `alembic check` model/index drift | Pre-existing autogenerate noise (pgvector/indexes); DB **upgrade head** succeeds; full autogen cleanup deferred |

## Backend ↔ frontend matrix

Authoritative table: [`docs/capability-matrix.md`](capability-matrix.md) + `capability-matrix.json`.

Summary:

- **User-facing UI:** projects, calendar, AI studio, chat, platform workspace, profile, notifications, dashboard
- **Admin UI:** users (+ embedded policy), settings, platform admin, RAG indexes/evaluation, jobs, diagnostics, observability
- **Embedded:** policy, memory, developer diagnostics
- **API-only / internal:** storage (health chips only), audit, parts of memory agent APIs, webhooks/internal tags

## Performance

| Finding | Evidence | Remediation |
| --- | --- | --- |
| Admin metrics user COUNTs | Bottleneck audit | Collapsed counts (`test_admin_metrics_query`) |
| Worker readiness Redis hammering | Startup docs | TTL cache (~25s) + active-module queues |
| Bundle budgets | `npm run check:budgets` | Warn-only on router/PWA precache; under max |

Details: [`docs/api-bottleneck-audit.md`](api-bottleneck-audit.md), [`docs/startup-dependencies.md`](startup-dependencies.md).

## Security

- Auth cookies + CSRF + rate limits + security headers preserved
- Dependency baseline: [`docs/dependency-security.md`](dependency-security.md) (FE residual **dev-only**; BE lock clean at last audit)
- Config contract prevents shipping required Settings without examples/OpenAPI export coverage
- Permission catalog still authoritative on backend; FE gates are UX only

## UX

| Area | Change |
| --- | --- |
| RAG Evaluation / Indexes | Tabbed compact UX, drawers, confirms |
| Admin Users / Jobs / Diagnostics | Thin views + hooks/components |
| Profile | Memory section when module active |
| Platform admin | Storage health card |
| Inactive modules | `NotFoundView` (not silent logout) |
| Primitives | `InfoTooltip`, `ConfirmDialog`, `IdCell`, `EmptyState`, `SectionTitleWithHelp` |

## Tests

| Layer | Coverage added/updated |
| --- | --- |
| Config | `test_config_contract.py` |
| Architecture | `test_architecture_rules.py`, generator `ArchitectureGuaranteesTest` |
| OpenAPI | `test_openapi_export.py` |
| FE unit | page registry, nav consistency, ModuleRouteGate, a11y, EmptyState, view orchestration |
| E2E | `architecture-smoke.spec.ts` (core vs rag gating, admin, logout, 404) |
| Fixes | retrieval cache + OTEL idempotency tests |

Verification snapshot (this phase):

- `ruff check backend` — pass
- `pytest backend/tests backend/modules` (excl. integration) — **531 passed**, 21 skipped
- `npm run lint` / `test` / `build` / `api:check` / `api:contract:check` / `test:e2e` — pass
- `alembic upgrade head` — pass; `alembic check` — **fails** (autogenerate drift; deferred)

## Remaining debt

1. `alembic check` index/FK drift vs models (pgvector / historical indexes) — reconcile carefully, do not blind-autogen
2. ~29 OpenAPI orphans — productize or extend intentional api-only allow-list when intentional
3. Migrate remaining Class C `frontend/src/api/*` to Orval wrappers
4. FE budget warn on router chunk / PWA precache — trim or rebase baselines when intentional
5. Residual npm audit (Orval/Vite/Vitest majors) — documented acceptances
6. Broader `is_admin` → capability RBAC replacement where still used
7. Live multi-profile provisioned E2E beyond mocked architecture smoke

## Final directory trees

### `backend/modules`

```text
backend/modules/
  admin/  ai/  audit/  calendar/  chat/
  developer_diagnostics/  diagnostics/
  identity_access/  jobs/  manifests/  memory/
  notifications/  platform/  policy/  profile/
  projects/  rag/  settings/  storage/  users/
```

### `backend/api`

```text
backend/api/
  main.py
  router.py
  router_registry.py
  deps/          # auth, admin, db
  middleware/    # csrf, correlation, rate limit, security headers, logging
  v1/
    health.py    # intentional shared health only
```

### `frontend/src/app`

```text
frontend/src/app/
  pageKeys.json
  pageRegistry.ts
  router.tsx
  providers.tsx
  theme.ts
  designTokens.ts
  SnackbarProvider.tsx
  …
```

### `frontend/src/features`

```text
frontend/src/features/
  admin-diagnostics/  admin-jobs/  admin-rag/  admin-users/
  ai/  auth/  calendar/  chat/  dashboard/
  developer-diagnostics/  notifications/  observability/
  platform/  platform-admin/  profile/  projects/
  settings-admin/  shell/
```

### `frontend/src/components`

```text
frontend/src/components/
  auth/  dashboard/  guards/  layout/
  notifications/
  ui/   # PageShell, QueryBoundary, EmptyState, ConfirmDialog, …
```

---

**Verdict:** Architecture is easier to extend than before — one ownership path for HTTP and pages, explicit surfaces/profiles, generator + contracts guarding regressions. Remaining items above are intentional debt, not blockers to the Phase 0–10 acceptance bar.
