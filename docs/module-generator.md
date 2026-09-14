# Module / scaffold generator

Create new application modules with a deterministic scaffold that follows this
repo's modular monolith conventions (manifests, FastAPI routers, policy deps,
optional Celery/frontend).

## Usage

From the repository root:

```bash
./scripts/generic-app create-module --help
./scripts/generic-app create-module orders --crud --frontend --permissions
```

Or via Python module:

```bash
PYTHONPATH=. uv run --project backend python -m backend.tools.generic_app create-module inventory
```

### Options

| Flag | Effect |
| --- | --- |
| `--crud` | SQLAlchemy model, repository, service, schemas, CRUD routes, Alembic revision, service tests |
| `--frontend` | React feature under `frontend/src/features/<module>/` (requires `--crud`) |
| `--celery` | Worker stub + `celery_queues` on the manifest |
| `--permissions` | `{module}.read` / `{module}.manage` on routes + policy catalog constants |
| `--events` | Outbox-ready event helper (requires `--crud`) |
| `--storage` | Declare `storage` dependency / health check on the manifest |
| `--no-wire` | Skip patching registry, API router, Alembic env, policy catalog |
| `--dry-run` | Print planned files without writing |
| `--force` | Overwrite existing generated files |
| `--entity` | Singular entity key (default: singularized module name) |

## What gets wired

Unless `--no-wire` is set, the generator patches:

- `backend/modules/manifests/registry.py` — intentional manifest import + registration
- `backend/api/router.py` — `/api/v1/<module>` mount
- `backend/alembic/env.py` — model import when `--crud`
- `backend/modules/policy/catalog.py` — permission constants when `--permissions`

Review the Alembic `down_revision` before migrating — set it to the current head
if the template parent has moved.

## Design rules

- Templates live under `backend/tools/generic_app/templates/` (Jinja2) — no giant
  string concatenations in Python.
- Discovery is intentional: the registry is patched, never filesystem-scanned for
  plugins.
- No runtime `pip install` of module dependencies.
- Generated code must parse and follow shared auth/session/error patterns.

## Tests

```bash
UV_CACHE_DIR=/tmp/generic-app-uv PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  uv run --project backend pytest backend/tools/generic_app/tests -q
```

Golden snapshots live in `backend/tools/generic_app/tests/goldens/`. If templates
change intentionally, delete the suite directory and re-run once to regenerate,
then commit the updated fixtures.
