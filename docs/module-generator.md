# Module / scaffold generator

Create new application modules with a deterministic scaffold that follows this
repo's modular monolith conventions (manifests, FastAPI router registry, policy
deps, Celery contributions, frontend routes gated by capability profiles).

## Usage

From the repository root:

```bash
./scripts/generic-app create-module --help
./scripts/generic-app create-module orders --crud --frontend --permissions --celery --optional
./scripts/generic-app create-module inventory --crud --frontend --profile rag
```

Or via Python module:

```bash
PYTHONPATH=. uv run --project backend python -m backend.tools.generic_app create-module inventory
```

### Options

| Flag | Effect |
| --- | --- |
| `--crud` | SQLAlchemy model, repository, service, schemas, CRUD routes, Alembic revision, service tests |
| `--frontend` | React feature + router/nav wiring (requires `--crud`) |
| `--celery` | Worker stub + queue + `celery_contrib` task route/module registration |
| `--permissions` | `{module}.read` / `{module}.manage` on routes + policy catalog constants |
| `--events` | Outbox-ready event helper (requires `--crud`) |
| `--storage` | Declare `storage` dependency / health check on the manifest |
| `--optional` | Default. Pack-toggle module (`always_enabled=False`, `optional=True`) |
| `--core` | Required core module (`always_enabled=True`) |
| `--profile NAME` | Profile-selected specialist (`optional=False`) + append to that profile |
| `--no-wire` | Skip marker-based wiring |
| `--dry-run` | Print planned files without writing |
| `--force` | Overwrite existing generated files |
| `--entity` | Singular entity key (default: singularized module name) |

Default enablement is `--optional` so generated business modules do **not** become
mandatory in every capability profile.

## What gets wired

Unless `--no-wire` is set, the generator patches stable marker sections:

| Target | Markers |
| --- | --- |
| `backend/modules/manifests/registry.py` | manifest imports + `REGISTERED_MANIFESTS` entries |
| `backend/api/router_registry.py` | `RouterContribution` entries (Phase 1 runtime gating) |
| `backend/alembic/env.py` | model imports when `--crud` |
| `backend/modules/policy/catalog.py` | permission constants/entries when `--permissions` |
| `backend/modules/manifests/celery_contrib.py` | task routes + `GENERATED_TASK_MODULES` when `--celery` |
| `frontend/src/app/router.tsx` | lazy import + gated `<Route>` when `--frontend` |
| `backend/modules/platform/profiles.py` | `PROFILE_EXTRA_MODULES` when `--profile` |

Alembic `down_revision` is resolved programmatically:

* one head → that revision
* zero heads → `None` (bootstrap)
* multiple heads → generation fails (no guessing)

Generation is atomic: if wiring fails after files are written, a mutation journal
rolls back created/patched files and the CLI exits non-zero.

## Design rules

- Templates live under `backend/tools/generic_app/templates/` (Jinja2).
- Discovery is intentional: registries are patched via markers, never filesystem-scanned.
- No runtime `pip install` of module dependencies.
- Wiring is deterministic, idempotent, and order-stable.
- Generated frontend routes use `ModuleRouteGate` / `page_key` so inactive profiles
  cannot mount the feature.

## Tests

```bash
UV_CACHE_DIR=/tmp/generic-app-uv PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  uv run --project backend pytest backend/tools/generic_app/tests -q
```

Golden snapshots live in `backend/tools/generic_app/tests/goldens/`. If templates
change intentionally, delete the suite directory and re-run once to regenerate,
then commit the updated fixtures.
