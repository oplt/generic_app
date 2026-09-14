# Feature module manifests

Declarative module metadata lives beside each module as `manifest.py` and is
registered intentionally in `backend/modules/manifests/registry.py`.

This is an internal application-module system — not a plugin marketplace. The
registry imports known manifests only; it does not scan the filesystem or
execute untrusted code.

## Manifest fields

See `backend/modules/manifests/types.py`:

- identity: `key`, `version`, `label`, `description`
- graph: `dependencies`, `always_enabled` / `optional`
- backend: `backend_router_keys`, `celery_queues`, `scheduled_tasks`,
  `settings_prefixes`, `health_checks`, `database_requirements`
- authz: `required_permissions` (Phase 4 capability keys)
- frontend: `nav_entries`, `frontend_routes` (`page_key` allow-list ids)

## Discovery & validation

```python
from backend.modules.manifests import validate_registry, effective_modules

validate_registry()  # startup — unknown deps / cycles fail clearly
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

## Example dependency

`rag` depends on `ai` and `storage`. Enabling a module whose dependency is off
fails with `ModuleManifestError`.
