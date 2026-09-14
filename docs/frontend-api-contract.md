# Frontend API contract

Ordinary request/response contracts come from the Orval-generated OpenAPI client under
`frontend/src/generated/`. Handwritten code under `frontend/src/api/` is classified as:

| Class | Meaning | Examples |
| --- | --- | --- |
| **A** | Transport / auth infrastructure — keep | `client.ts`, `axiosClient.ts`, `orvalMutator.ts` |
| **B** | Compatibility wrapper around generated clients — prefer | `jobs.ts`, `diagnostics.ts`, `policy.ts`, `ragIndexes.ts`, `ragEvaluation.ts`, `admin.ts`, `memory.ts`, `profile.ts` |
| **C** | Duplicate endpoint implementation — migrate toward B | `ai.ts`, `auth.ts`, `projects.ts`, `calendar.ts`, … |
| **D** | Generator-unfriendly specials — document | cookie/CSRF + refresh single-flight in `client.ts`; event helpers |

## Coverage report (Phase 7)

```bash
cd frontend
npm run api:contract          # write docs/api-contract-coverage.{json,md}
npm run api:contract:check    # same + exit 1 on true violations
npm run api:contract:unit     # allow-list / path-normalization unit tests
```

Each OpenAPI operation is classified:

| Class | Meaning |
| --- | --- |
| `ui_used` | Called via generated SDK and/or handwritten feature wrapper |
| `programmatic_api_only` | Listed in `frontend/openapi/intentional-api-only.json` |
| `health_observability` | Health / observability / developer-diagnostics |
| `internal` | Webhooks and similar |
| `currently_orphaned` | In OpenAPI + SDK but no frontend caller (informational) |

**CI fails only** when:

* OpenAPI operation missing from generated SDK
* Generated path missing from OpenAPI
* Stale import of a generated `*ApiV1*` symbol

Orphans and intentional API-only endpoints do **not** fail CI.

Machine report: [`api-contract-coverage.md`](api-contract-coverage.md) /
[`api-contract-coverage.json`](api-contract-coverage.json).

## Enforcement

* `npm run api:check` — schema + generated client must match FastAPI export (CI mandatory).
* `npm run api:contract:check` — structural OpenAPI↔SDK↔import integrity.
* `src/api/rawApiPathGuard.test.ts` — no new raw `/api/v1/...` string literals outside the allow-list
  (`src/generated/**` plus transport/test helpers listed in that file).

## Regenerating

```bash
cd frontend && npm run api:generate && npm run api:contract
```
