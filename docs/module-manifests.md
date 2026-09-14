# Feature module manifests

Declarative module metadata lives beside each module as `manifest.py` and is
registered intentionally in `backend/modules/manifests/registry.py`.

This is an internal application-module system — not a plugin marketplace. The
registry imports known manifests only; it does not scan the filesystem or
execute untrusted code.

Adding a feature end-to-end: [adding-a-feature.md](adding-a-feature.md).
Scaffolding: [module-generator.md](module-generator.md).

## Manifest fields

See `backend/modules/manifests/types.py`:

- identity: `key`, `version`, `label`, `description`
- graph: `dependencies`, `always_enabled` / `optional`
- surface: `surface` (`ModuleSurface`), optional `embedding_host`, `user_visible`
- backend: `backend_router_keys`, `celery_queues`, `scheduled_tasks`,
  `settings_prefixes`, `health_checks`, `database_requirements`
- authz: `required_permissions` (capability keys in the policy catalog)
- frontend: `nav_entries`, `frontend_routes` (`page_key` allow-list ids)

### ModuleSurface

| Value | Meaning |
| --- | --- |
| `user_facing` | Primary workspace UI (nav + gated routes) |
| `admin_facing` | Admin console surfaces |
| `embedded` | Hosted inside another page (e.g. policy panels on Admin Users) |
| `api_only` | HTTP/API without a dedicated product page |
| `internal` | Platform plumbing; not product navigation |

Generators set `USER_FACING` when `--frontend` is passed, otherwise `API_ONLY`.
Change the enum (and `embedding_host` for embedded hosts) intentionally — do not
infer visibility from an empty `frontend_routes` tuple.

`FrontendRoute.page_key` values must exist in
`frontend/src/app/pageKeys.json` (validated at registry load).

## Discovery & validation

```python
from backend.modules.manifests import validate_registry, effective_modules

validate_registry()  # startup — unknown deps / cycles / bad page_keys fail clearly
enabled = effective_modules(["billing", "webhooks"])
```

Startup calls `validate_registry()` from the FastAPI lifespan.

`PlatformConfigService` resolves pack + overrides, then `effective_modules(...)`
to ensure optional modules have their dependencies satisfied. Metadata exposes:

- `enabled_modules` — optional pack toggles (API compatibility)
- `active_modules` — full effective set including always-on core
- `module_nav` / `module_routes` — frontend contributions

`MODULE_CATALOG` in `platform/defaults.py` is derived from optional manifests.
`MODULE_PACKS` is derived from [capability profiles](capability-profiles.md).

## Frontend

`useModuleNavigation()` reads `module_nav` and maps allow-listed `icon` keys to
MUI icons. No dynamic code loading.

Inactive modules render `NotFoundView` via `ModuleRouteGate` (page_key in
`module_routes`, with `active_modules` as a legacy fallback) — they do not look
like a silent logout.

## Example dependency

`rag` depends on `ai` and `storage`. Enabling a module whose dependency is off
fails with `ModuleManifestError`.
