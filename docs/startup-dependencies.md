# Startup dependency classification

Source: `backend/api/main.py` lifespan + `/health/ready`.

| Dependency | Class | Startup | Ready | Notes |
| --- | --- | --- | --- | --- |
| Module / capability validation | **hard** | abort | n/a | Bad manifests/profiles must not boot |
| RAG / memory config validation | **capability** | abort if module active | n/a | Inactive specialists skip validation |
| Postgres + platform defaults | **hard** | abort | required | Seed must succeed; no fail-open writes |
| Redis ping | **soft** | log + continue | required | Cache/rate-limit degrade; ready still needs Redis |
| Object storage bucket bootstrap | **capability** | soft log | required only if `storage` ∈ profile `health_checks` | Core/lean: not required even if `STORAGE_BUCKET` set |
| pgvector | **capability** | n/a at boot | required when `vector` ∈ `health_checks` | Declared by `rag` |
| Celery workers / queues | **soft at boot** | metrics loop only | required | Queue set follows active modules |

## Intentional asymmetry

Redis and storage **bootstrap** soft-fail at startup so a misconfigured optional MinIO does not brick a core profile. `/health/ready` remains strict for **required** checks so traffic is not accepted while hard deps are down.

Platform defaults **hard-fail** at startup: without Postgres seed the app cannot serve coherent config.

## Storage gating

`storage` / `vector` readiness come from `resolve_active_modules().health_checks`, not from “bucket env var set”.

- `rag` declares `health_checks=("vector", "storage")`
- always-on `storage` / `observability` modules do **not** force object-storage readiness

## Layers

1. **Config parse** — `backend.core.config.settings`
2. **App construct** — `create_app(include_lifespan=…)` (OpenAPI uses `False`)
3. **Lifespan runtime** — validation, soft probes, hard seed, worker metrics loop

See also: [dependency-degradation.md](runbooks/dependency-degradation.md).
