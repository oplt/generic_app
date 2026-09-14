# Dependency security baseline (Phase 0)

Recorded after repairing CI and applying non-breaking upgrades.
Do **not** use `npm audit fix --force`.

## Frontend (`npm audit`)

Reduced from 28 → 6 findings (2026-09-14).

### Fixed / mitigated

- Direct runtime bumps: `react-router-dom@7.18.3`, `axios@1.20.0`
- Dev bumps within major: `vitest` / `@vitest/coverage-v8` → 3.2.7
- `npm audit fix` (no `--force`) for transitive patches
- `overrides`: `lodash@^4.18.1`, `js-yaml@4.3.2`

### Accepted residual (require breaking majors)

| Package | Severity | Kind | Why accepted |
| --- | --- | --- | --- |
| `orval` ≤8.21 | critical | **dev-only** codegen | Exploit needs hostile OpenAPI/`$ref` at generate time. We only generate from our own FastAPI schema. Orval 8 is a breaking upgrade — defer. |
| `vite` / `esbuild` | high/moderate | **dev-only** | Affects Vite/esbuild **dev server**, not production build artifacts. Vite 8 is breaking — defer. |
| `vitest` / `@vitest/*` | moderate | **dev-only** | Vitest UI / mocker path issues. CI uses `vitest run` (no UI). Vitest 5 is breaking — defer. |

## Backend (`pip-audit` on exported prod lock)

After `uv lock --upgrade-package` for affected libs: **no known vulnerabilities**.

Upgraded notably: `aiosmtplib`, `pyjwt`, `python-multipart`, `pydantic-settings`, `pypdf`, `starlette`, `urllib3`, plus transitive `click` / `h2` / `idna` / `mako` / `langsmith`.
