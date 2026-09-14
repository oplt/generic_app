# Adding a feature

Canonical path for extending this starter. Prefer the module generator for the
boilerplate, then fill in domain logic. You should **not** hand-edit five
unrelated central files for every feature — the generator wires the marked
registration seams.

## One-command scaffold

```bash
./scripts/generic-app create-module orders \
  --crud --frontend --permissions --celery --optional
```

That creates the module package, optional Alembic revision, policy keys, Celery
stub, React feature view, and patches:

| Seam | File |
| --- | --- |
| Manifest registry | `backend/modules/manifests/registry.py` |
| HTTP mount | `backend/api/router_registry.py` |
| Models (CRUD) | `backend/alembic/env.py` |
| Permissions | `backend/modules/policy/catalog.py` |
| Celery | `backend/modules/manifests/celery_contrib.py` |
| Page allow-list | `frontend/src/app/pageKeys.json` + `pageRegistry.ts` |
| Profile extras | `backend/modules/platform/profiles.py` (with `--profile`) |

Details: [module-generator.md](module-generator.md).

## Manual checklist (same architecture)

Use this when editing by hand or extending a generated module.

### 1. Domain / service / repository

- Package: `backend/modules/<key>/`
- Typical layout: `application/service.py`, `infrastructure/{models,repository}.py`,
  `api/{router,schemas}.py`, `manifest.py`
- Shared helpers live in `backend/lib/` — do not copy Redis/pagination utilities

### 2. Router

- Own the HTTP surface in `backend/modules/<key>/api/router.py`
- Register a `RouterContribution` in `backend/api/router_registry.py`
- **Do not** add feature routes under `backend/api/v1/` (health-only)

### 3. Manifest

- Declare `ModuleManifest` with explicit `ModuleSurface`
  (`user_facing` / `admin_facing` / `embedded` / `api_only` / `internal`)
- Dependencies, `backend_router_keys`, `required_permissions`,
  `nav_entries` / `frontend_routes` as needed
- Import into `REGISTERED_MANIFESTS` ([module-manifests.md](module-manifests.md))

### 4. Permissions

- Add capability keys to `backend/modules/policy/catalog.py`
- Protect routes with `require_permission("…")`
- Mirror keys on the manifest `required_permissions` tuple
- See [policy-rbac.md](policy-rbac.md)

### 5. Frontend page registry

- Implement the view under `frontend/src/features/<feature>/views/`
- Add the `page_key` to `pageKeys.json` and a `page(...)` entry in `pageRegistry.ts`
- Routes auto-mount from the registry; **do not** recreate `src/pages/` re-exports
- Gate with `ModuleRouteGate` via `moduleKey` on the registration

### 6. Navigation contribution

- Prefer `NavEntry` on the module manifest (`module_nav` from platform metadata)
- Frontend maps allow-listed icons in `useModuleNavigation` — add an icon key there
  only when you need a non-default glyph

### 7. API generation

```bash
cd frontend && npm run api:generate
```

Prefer Orval-generated clients / wrappers under `frontend/src/api/`
([openapi-frontend-sdk.md](openapi-frontend-sdk.md),
[frontend-api-contract.md](frontend-api-contract.md)).

### 8. Capability profile

- Optional modules stay off until a pack/profile enables them
- Append with `--profile <key>` or edit `PROFILE_EXTRA_MODULES`
- See [capability-profiles.md](capability-profiles.md)

### 9. Tests

- Module: `backend/modules/<key>/tests/`
- Architecture rules: [testing-architecture.md](testing-architecture.md)
- After OpenAPI changes: `npm run api:check` / `npm run api:contract:check`

## Enablement

| Flag / setting | Effect |
| --- | --- |
| `--optional` (default) | Pack toggle; not on in every profile |
| `--core` | Always-on core graph |
| `--profile NAME` | Specialist module appended to that profile |
| Admin “Capability profile” | Runtime `platform.module_pack` |

## Anti-patterns (deleted on purpose)

- Feature routers under `backend/api/v1/`
- Parallel `frontend/src/pages/*` re-export layer
- Guessing frontend exposure from empty routes — always set `ModuleSurface`
- Scanning the filesystem for manifests/plugins at runtime
- Module-private Redis clients instead of `backend/lib/app_cache`
