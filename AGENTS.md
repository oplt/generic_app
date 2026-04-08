# Repository Guidelines

## Project Structure & Module Organization
This repo is split by runtime. `backend/` contains the FastAPI app, Celery workers, Alembic migrations, and tests. Key areas are `backend/api/`, `backend/modules/`, `backend/core/`, and `backend/alembic/versions/`. `frontend/` contains the React + Vite client with `src/pages/`, `src/components/`, `src/features/`, `src/api/`, and `src/test/`. Infrastructure lives in `infra/`; architecture notes live in `docs/adr/`.

## Build, Test, and Development Commands
Use the commands from each app directory.

- `cd frontend && npm run dev`: start the Vite dev server.
- `cd frontend && npm run build`: type-check and build the production bundle.
- `cd frontend && npm run lint`: run ESLint on TS/TSX files.
- `cd frontend && npm run test` or `npm run test:coverage`: run Vitest once, with optional coverage output.
- `cd backend && uv sync`: install backend dependencies into `.venv`.
- `cd backend && .venv/bin/uvicorn backend.api.main:app --reload`: run the API locally.
- `cd backend && .venv/bin/alembic upgrade head`: apply database migrations.
- `docker compose -f infra/docker-compose.yml up -d`: start PostgreSQL, Redis, and MinIO.

## Coding Style & Naming Conventions
Frontend code uses TypeScript with ESLint. Use PascalCase for React components (`PageHeader.tsx`), camelCase for hooks and utilities (`useAuth.ts`), and keep API modules grouped by domain. Backend Python follows Ruff with a 100-character line length. Use snake_case for Python modules and keep routers, schemas, services, and repositories aligned inside each module directory.

## Testing Guidelines
Frontend tests use Vitest with a `jsdom` environment and shared setup in `frontend/src/test/setup.ts`. Place new tests beside the feature as `*.test.ts` or `*.test.tsx`. Backend coverage is currently light; add tests under `backend/tests/` for new API, service, or migration behavior. Run affected frontend tests before opening a PR and note any backend checks performed manually if automation is missing.

## Commit & Pull Request Guidelines
Recent commits are short, lowercase summaries like `theme changed` and `calendar periods`. Keep commits focused and imperative, but more specific when possible, for example `add project detail route`. PRs should include a brief summary, linked issue if applicable, testing notes, and screenshots for visible frontend changes.

## Security & Configuration Tips
Auth and local infra are first-class parts of this repo. Keep secrets in `.env` files, never commit credentials, prefer secure `httpOnly` cookies over browser token storage, and review auth, authorization, validation, and CORS impacts for any API or session-related change.

# Repo rules

## Commands
- Backend checks: pnpm test && pnpm lint
- Security checks: pnpm audit --audit-level=high
- API schema validation lives in src/schemas
- Auth middleware lives in src/middleware/auth.ts
- Production env validation is in src/config/env.ts