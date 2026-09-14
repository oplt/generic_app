# Typed OpenAPI frontend SDK

FastAPI's OpenAPI schema is the source of truth for frontend request/response
types. We generate a TypeScript client with **Orval** (mature generator with
first-class TanStack React Query + optional Zod support).

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
```

From repo root:

```bash
./frontend/scripts/api-generate.sh
PYTHONPATH=. uv run --project backend python -m backend.scripts.export_openapi
```

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

Keep domain Zod forms (e.g. profile UI schemas) when they add UX validation
beyond the wire contract.

## CI

The frontend workflow runs `npm run api:check` so OpenAPI/client drift fails the
build.
