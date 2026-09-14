# Frontend API contract

Ordinary request/response contracts come from the Orval-generated OpenAPI client under
`frontend/src/generated/`. Handwritten code under `frontend/src/api/` is classified as:

| Class | Meaning | Examples |
| --- | --- | --- |
| **A** | Transport / auth infrastructure — keep | `client.ts`, `axiosClient.ts`, `orvalMutator.ts` |
| **B** | Compatibility wrapper around generated clients — prefer | `jobs.ts`, `diagnostics.ts`, `policy.ts`, `ragIndexes.ts`, `ragEvaluation.ts`, `admin.ts` |
| **C** | Duplicate endpoint implementation — migrate / remove | remaining feature modules (`ai.ts`, `auth.ts`, …) still on handwritten paths |
| **D** | Generator-unfriendly specials — document | cookie/CSRF + refresh single-flight in `client.ts`; streaming/SSE/upload paths when Orval cannot express them cleanly |

## Phase 6 migrations (complete)

Wrappers now call generated functions and re-export generated model types:

* jobs console
* admin diagnostics
* policy roles / assignments
* RAG index administration (including rollback)
* RAG evaluation workbench

Feature modules keep stable import paths (`../../../api/jobs`, etc.).

## Enforcement

* `npm run api:check` — schema + generated client must match the running FastAPI app (CI mandatory).
* `src/api/rawApiPathGuard.test.ts` — no new raw `/api/v1/...` string literals outside the allow-list
  (`src/generated/**` plus transport/test helpers listed in that file).

## Regenerating

```bash
cd frontend && npm run api:generate
```
