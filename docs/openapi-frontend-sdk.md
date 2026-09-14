# Typed OpenAPI frontend SDK

FastAPI's OpenAPI schema is the source of truth for frontend request/response
types. We generate a TypeScript client with **Orval** (mature generator with
first-class TanStack React Query + optional Zod support).

Place in the feature workflow: after the backend router exists, run
`npm run api:generate`, then wrap generated calls from `frontend/src/api/` or
feature code. See [adding-a-feature.md](adding-a-feature.md) and
[frontend-api-contract.md](frontend-api-contract.md).

## Why Orval

| Option | Fit |
| --- | --- |
| **Orval** (chosen) | React Query hooks, fetch/axios mutators, Zod client, tags-split output |
| openapi-typescript + openapi-fetch | Excellent types; weaker React Query ergonomics out of the box |
| openapi-generator | Heavy JVM toolchain; awkward with Vite/RQ |

Generated calls use a **custom fetch mutator** (`src/api/orvalMutator.ts`) that
delegates to `apiFetch` (cookies, CSRF, refresh). An Axios instance with the
same auth headers lives at `src/api/axiosClient.ts` if you later switch Orval's
`httpClient` to `axios`.

## Commands

From `frontend/`:

```bash
npm run api:generate   # export OpenAPI + Orval generate
npm run api:check      # regenerate and fail on git drift
npm run api:contract   # write docs/api-contract-coverage.{json,md}
npm run api:contract:check
```

From repo root (OpenAPI export alone — no live Postgres/Redis/MinIO required):

```bash
./frontend/scripts/api-generate.sh
PYTHONPATH=. uv run --project backend python -m backend.scripts.export_openapi
```

Export uses `Settings.for_openapi_export()` + `create_app(include_lifespan=False)`
so CI and local generation stay infrastructure-light
([startup-dependencies.md](startup-dependencies.md)).

## Layout

```text
frontend/openapi/openapi.json          # exported FastAPI schema (committed)
frontend/orval.config.ts
frontend/src/generated/
  endpoints/<tag>/                     # React Query hooks + fetch functions
  models/                              # request/response TypeScript types
  zod/                                 # Zod schemas (optional validation)
  index.ts                             # re-exports models
frontend/src/api/orvalMutator.ts
frontend/src/api/axiosClient.ts
```

Every generated file starts with `DO NOT EDIT MANUALLY`.

## Adoption

Prefer generated types/functions for new feature work. Existing hand-written
`src/api/*` modules can wrap generated endpoints (see `src/api/profile.ts`) so
call sites stay stable while contracts come from OpenAPI.

Scaffolded module clients under `features/<key>/api.ts` start as thin `apiFetch`
wrappers; migrate them to Orval after the first OpenAPI export that includes the
new tag.

Keep domain Zod forms (e.g. profile UI schemas) when they add UX validation
beyond the wire contract.

## CI

The frontend workflow runs:

1. `npm run api:check` — OpenAPI/client drift fails the build
2. `npm run api:contract:check` — coverage violations (missing SDK ops / stale imports)

Coverage artifacts land in `docs/api-contract-coverage.*` (also uploaded from CI).
