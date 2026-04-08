# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack SaaS starter with FastAPI (Python) backend and React + Vite (TypeScript) frontend. Multi-tenant capable with auth, projects, calendar, admin panel, and email workflows.

## Commands

### Infrastructure (must be running)
```bash
docker compose -f infra/docker-compose.yml up -d   # PostgreSQL, Redis, MinIO
```

### Backend
```bash
cd backend
uv sync                                             # Install dependencies
cp .env.example .env                                # First-time setup
.venv/bin/alembic upgrade head                      # Run migrations
.venv/bin/uvicorn backend.api.main:app --reload     # Dev server (port 8000)
.venv/bin/celery -A backend.workers.celery_app:celery_app worker --loglevel=INFO --queues=default,email  # Worker
```

### Frontend
```bash
cd frontend
npm install
npm run dev          # Dev server (port 5173)
npm run build        # TypeScript check + Vite build
npm run lint         # ESLint
npm run test         # Vitest
npm run test:watch
npm run test:coverage
```

## Architecture

### Backend (`backend/`)

**Module structure** — each feature lives under `backend/modules/<name>/` with its own models, schemas, router, service, and repository.

Key modules: `identity_access` (auth), `users`, `projects`, `calendar`, `admin`, `platform`, `settings`, `notifications`, `audit`, `profile`.

**Auth flow**: JWT access + refresh tokens in httpOnly cookies. Refresh token rotation — old token revoked on each refresh. Verification and password-reset tokens stored in Redis with TTL. MFA via TOTP (pyotp).

**Data layer**: SQLAlchemy 2.0 async (asyncpg), repository pattern. Alembic for migrations.

**Async jobs**: Celery with Redis broker for email delivery. Set `CELERY_TASK_ALWAYS_EAGER=true` in `.env` to run tasks inline during development.

**Config**: All settings via `backend/core/config.py` (pydantic-settings). Environment variables from `.env`.

Notable env vars:
- `CORE_DOMAIN_SINGULAR` / `CORE_DOMAIN_PLURAL` — rename the "project" concept app-wide
- `PLATFORM_DEFAULT_MODULE_PACK` — feature set selection (`lean_saas`, `automation_suite`, `client_portal`, `full_platform`)
- `ADMIN_SIGNUP_INVITE_CODE` — optional invite code for admin registration

### Frontend (`frontend/src/`)

**Routing**: React Router v7 with lazy-loaded pages. Protected routes via auth guard. Admin routes check role.

**State**:
- Auth: custom Context + `authStore` (holds access token in memory)
- Server state: TanStack Query v5 (5-min stale time)
- UI: MUI theme context (system/light/dark)

**API client** (`api/`): `apiFetch` wrapper handles Bearer token injection, automatic 401 → refresh retry (deduplicated), and error extraction. Per-module API clients consume it.

**Design system**: Mistral AI-inspired theme — warm orange/amber palette, sharp corners (no border-radius), golden shadow system, large display typography. Defined in `app/theme.ts`. See `DESIGN.md` for full spec; follow it when adding UI.

## Security Conventions

- Auth tokens in httpOnly cookies only — never localStorage
- CORS restricted to `FRONTEND_URL`
- Silent failure on identity checks (don't leak user existence in error messages)
- Argon2 password hashing
- Wildcard CORS and missing authz/IDOR are treated as blockers
