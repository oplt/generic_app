# Frontend

React + TypeScript + Vite app for generic_app.

## OpenAPI TypeScript client

Typed request/response models and React Query hooks are generated from FastAPI's
OpenAPI schema (Orval). See [docs/openapi-frontend-sdk.md](../docs/openapi-frontend-sdk.md).

```sh
npm run api:generate   # export schema + regenerate src/generated/
npm run api:check      # fail CI/local when artifacts drift
```

## End-to-end tests (Playwright)

The default suite is **mocked Chromium smoke**. It does not need a backend or credentials.

```sh
cd frontend
npm ci
npm run test:e2e:install    # downloads Chromium only (required once per machine/CI image)
CI=1 npm run test:e2e       # mocked smoke; Firefox/WebKit are not installed by default
```

| Script | Purpose |
| --- | --- |
| `npm run test:e2e:install` | Install the declared default browser (`chromium`) |
| `npm run test:e2e:install:all` | Install Chromium, Firefox, and WebKit |
| `npm run test:e2e` | Mocked smoke (`@provisioned` tests excluded) |
| `npm run test:e2e:provisioned` | Credential-backed flows only (`E2E_PROVISIONED=1`) |

Browsers are selected with `E2E_BROWSERS` (comma-separated). Default is `chromium`. Example:

```sh
npm run test:e2e:install:all
E2E_BROWSERS=chromium,firefox,webkit npm run test:e2e
```

Provisioned tests need a running API/UI and credentials:

```sh
export E2E_BASE_URL=http://localhost:5173
export E2E_API_URL=http://localhost:8000
export E2E_TEST_EMAIL=...
export E2E_TEST_PASSWORD=...
# optional admin flows:
export E2E_ADMIN_EMAIL=...
export E2E_ADMIN_PASSWORD=...
npm run test:e2e:provisioned
```

If browsers are missing, Playwright fails with an install hint — that is a harness problem, not a UI regression. Install via `npm run test:e2e:install` before debugging selectors.

## CI quality gates and bundle/PWA budgets

GitHub Actions workflow: `.github/workflows/frontend.yml`.

On every pull request and push to `main` it runs:

1. `npm ci` (cached)
2. `npm run lint`
3. `npm run test` (Vitest)
4. `npm run build`
5. `npm run check:budgets` (per-chunk + PWA precache vs `budgets.json`)
6. `npm run test:e2e:install` + Chromium mocked smoke

Budgets are baseline-derived (~5% warn, ~15% fail). After an intentional size change, rebuild, inspect `budget-report.json`, and update `budgets.json` in the same PR.

```sh
npm run build
npm run check:budgets
```

## React + TypeScript + Vite template notes

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
