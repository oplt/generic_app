# Generic App

A modular full-stack application foundation built with FastAPI, React, PostgreSQL, Celery, and an optional AI/RAG stack, designed to be cloned and shaped into SaaS, workflow, client-portal, retrieval, or agent-style products.

## Table of Contents

* [Overview](#overview)
* [Key Features](#key-features)
* [Architecture](#architecture)
* [Technology Stack](#technology-stack)
* [Capability Profiles](#capability-profiles)
* [Repository Structure](#repository-structure)
* [Prerequisites](#prerequisites)
* [Current Main-Branch Notes](#current-main-branch-notes)
* [Quick Start](#quick-start)
* [Local Services](#local-services)
* [Configuration](#configuration)
* [Authentication and Security](#authentication-and-security)
* [Authorization and RBAC](#authorization-and-rbac)
* [Application Modules](#application-modules)
* [Module Generator](#module-generator)
* [AI and RAG Architecture](#ai-and-rag-architecture)
* [Background Jobs](#background-jobs)
* [Data and Storage](#data-and-storage)
* [API](#api)
* [Typed Frontend SDK](#typed-frontend-sdk)
* [Frontend Architecture](#frontend-architecture)
* [Design System](#design-system)
* [Caching, Idempotency, and Concurrency](#caching-idempotency-and-concurrency)
* [Observability](#observability)
* [Diagnostics and Failure Injection](#diagnostics-and-failure-injection)
* [Testing](#testing)
* [Code Quality](#code-quality)
* [CI](#ci)
* [Database Migrations](#database-migrations)
* [Development Workflow](#development-workflow)
* [Adding a Feature](#adding-a-feature)
* [Documentation Index](#documentation-index)
* [Troubleshooting](#troubleshooting)
* [Production Considerations](#production-considerations)
* [Security Notes](#security-notes)
* [Contributing](#contributing)
* [License](#license)

## Overview

Generic App is a reusable application foundation rather than a single-purpose product. The backend is organized as a modular monolith: feature modules are registered explicitly, their dependencies are validated at startup, and named capability profiles decide which specialist modules, routes, queues, navigation entries, and optional platform capabilities are active. The frontend consumes the same platform metadata to gate routes and navigation.

The repository provides the cross-cutting work that many applications otherwise rebuild repeatedly: authentication, users and profiles, projects and organization-aware tenancy, capability-based authorization, background jobs, object storage, notifications, platform settings, generated API contracts, caching, idempotency, observability, diagnostics, and test infrastructure.

For AI-oriented products, the repository also contains an optional AI/RAG stack. It supports provider-backed generation, document ingestion, pgvector retrieval, PostgreSQL full-text search, reciprocal-rank fusion, cited answers, index versioning, evaluation tooling, document-grounded chat, and memory integration. These capabilities are selected through the `rag`, `agent`, or `full_platform` capability profiles rather than being mandatory for every clone.

The intended extension model is explicit and controlled: application modules live under `backend/modules/`, frontend features are colocated under `frontend/src/features/`, manifests describe module contributions, and the `generic-app` scaffold generator can create and wire new modules without runtime plugin discovery.

## Key Features

### Application foundation

* FastAPI API with a versioned `/api/v1` application router.
* React + TypeScript + Vite frontend with lazy-loaded routes.
* PostgreSQL persistence through async SQLAlchemy and Alembic migrations.
* Authentication with short-lived JWT access tokens and rotating refresh sessions.
* Email verification, password reset, admin invite signup, and TOTP MFA support.
* User/profile, project, notification, calendar, settings, platform, and admin modules.
* Organization/project-aware tenancy and authorization boundaries.

### Platform capabilities

Optional modules can be selected by capability profile:

* Billing and subscription-plan management.
* User-managed API keys.
* Outbound webhooks.
* Feature flags.
* Customizable transactional email templates.

### AI, RAG, and agent capabilities

* Built-in local heuristic AI provider for development/test flows.
* OpenAI generation and embedding adapter.
* Anthropic generation adapter.
* Document upload, parsing, chunking, embedding, indexing, retrieval, and cited answers.
* Supported RAG file types: PDF, TXT, Markdown, DOCX, and CSV.
* PostgreSQL + pgvector vector storage with a 1536-dimension schema and HNSW index.
* PostgreSQL full-text lexical retrieval.
* `vector`, `lexical`, and `hybrid_rrf` retrieval strategies.
* Reciprocal Rank Fusion and optional post-retrieval reranking.
* Versioned RAG indexes, stale-document detection, reindex workflows, and rollback/activation tooling.
* RAG evaluation datasets, runs, retrieval metrics, comparison, and export.
* Document-grounded knowledge chat.
* Optional Mem0-backed memory integration.

### Background processing and reliability

* Celery workers with Redis broker/result backend.
* Capability-profile-aware task routing and queue selection.
* Transactional outbox flow for durable publication of background work.
* Celery Beat schedules for outbox dispatch, idempotency cleanup, and module-specific maintenance.
* Shared cache abstraction with Redis, invalidation tags, generations, negative caching, and single-flight loading.
* HTTP `Idempotency-Key` framework and durable external-effect ledger.
* Bounded concurrency, timeouts, selective retries, backoff, and provider limiters.

### Developer platform

* Declarative per-module manifests and dependency validation.
* Named capability profiles for common starter shapes.
* Module/scaffold generator with backend, frontend, permissions, Celery, events, storage, and Alembic wiring.
* FastAPI OpenAPI schema exported into an Orval-generated TypeScript/React Query SDK.
* Feature-colocated frontend organization.
* PWA build configuration.

### Operations and quality

* JSON application logging with correlation/request IDs.
* Prometheus metrics.
* OpenTelemetry tracing with OTLP exporters.
* Optional Sentry integration.
* Grafana/Prometheus/Tempo local observability configuration.
* Infrastructure diagnostics and per-request developer diagnostics.
* Local/test-only failure injection for resilience testing.
* Pytest backend tests, Vitest frontend tests, Playwright E2E tests, Ruff, ESLint, TypeScript builds, OpenAPI drift checks, and bundle/PWA budgets in CI.

## Architecture

The runtime is a modular monolith: one FastAPI application mounts only the router contributions associated with the active capability profile. The same resolved module set drives Celery task routing and frontend route/navigation metadata.

```mermaid
flowchart TB
    User[Browser / User]

    subgraph Frontend[React + Vite Frontend]
        UI[Feature UI]
        Router[React Router + ModuleRouteGate]
        Query[TanStack Query]
        SDK[Generated OpenAPI SDK]
        Client[Cookie + CSRF API client]
        UI --> Router
        Router --> Query
        Query --> SDK
        SDK --> Client
    end

    subgraph API[FastAPI Modular Monolith]
        Entry[FastAPI app]
        Registry[Capability profile + manifest registry]
        Modules[Application modules]
        Policy[Policy / RBAC]
        Entry --> Registry
        Registry --> Modules
        Modules --> Policy
    end

    subgraph Jobs[Background Processing]
        Outbox[Transactional outbox]
        Beat[Celery Beat]
        Workers[Celery workers]
        Beat --> Outbox
        Outbox --> Workers
    end

    DB[(PostgreSQL / pgvector)]
    Redis[(Redis)]
    Storage[(S3-compatible storage / MinIO)]
    Mail[SMTP / Mailpit]
    Providers[AI providers / external integrations]
    Obs[Prometheus / OpenTelemetry / Grafana / Tempo / Sentry]

    User --> UI
    Client --> Entry
    Modules --> DB
    Modules --> Redis
    Modules --> Storage
    Modules --> Outbox
    Workers --> DB
    Workers --> Redis
    Workers --> Storage
    Workers --> Mail
    Modules --> Providers
    Workers --> Providers
    Entry --> Obs
    Workers --> Obs
```

### Architectural principles

**Modular monolith.** Feature code is grouped under `backend/modules/`. Modules are registered intentionally instead of discovered by scanning the filesystem. Their dependency graph is validated during FastAPI startup.

**Capability-driven bootstrap.** `backend/modules/platform/profiles.py` resolves the active profile into modules, router keys, Celery queues, scheduled tasks, permissions, health checks, frontend routes, and navigation entries. Runtime composition selects already-registered code; it does not install packages dynamically.

**Explicit cross-module boundaries.** Shared infrastructure belongs in core/shared abstractions rather than feature routers. The repository's contribution guidelines explicitly discourage importing another feature's router as an integration mechanism or duplicating shared helpers.

**Durable asynchronous effects.** Long-running or failure-sensitive work crosses a Celery boundary. RAG ingestion uses a database outbox so the application transaction can commit the intent to perform work before a dispatcher publishes it to Celery.

**Contract-driven frontend.** FastAPI's OpenAPI schema is committed and used to generate TypeScript models, React Query hooks, and optional Zod schemas with Orval. The custom frontend transport preserves cookie authentication, CSRF protection, correlation IDs, and refresh behavior.

## Technology Stack

| Layer                | Technology                                        | Role                                                       |
| -------------------- | ------------------------------------------------- | ---------------------------------------------------------- |
| Backend language     | Python 3.12+                                      | API, domain, workers, tooling                              |
| API                  | FastAPI                                           | HTTP application and OpenAPI schema                        |
| ORM                  | SQLAlchemy async                                  | Relational persistence                                     |
| Migrations           | Alembic                                           | Database schema evolution                                  |
| Database             | PostgreSQL 16                                     | Primary relational and lexical-search store                |
| Vector search        | pgvector                                          | 1536-dimensional embeddings and HNSW retrieval             |
| Cache / broker       | Redis                                             | Cache, tokens, rate limiting, Celery broker/result backend |
| Background jobs      | Celery                                            | Async jobs, queues, scheduled work                         |
| Object storage       | Boto3 + S3-compatible API                         | Files and application assets; MinIO locally                |
| Email                | aiosmtplib                                        | Transactional SMTP delivery; Mailpit locally               |
| AI                   | Local heuristic, OpenAI, Anthropic adapters       | Generation; local/OpenAI embeddings                        |
| Memory               | Mem0 integration                                  | Optional agent memory                                      |
| Frontend             | React 19                                          | Application UI                                             |
| Frontend language    | TypeScript 5.9                                    | Typed UI and API integration                               |
| Build tool           | Vite 5                                            | Development/build pipeline                                 |
| Routing              | React Router 7                                    | Client-side routing                                        |
| UI                   | Material UI 7 + Emotion                           | Components and theming                                     |
| Server state         | TanStack Query 5                                  | Remote state and caching                                   |
| Forms                | React Hook Form + Zod                             | Form state and validation                                  |
| API generation       | Orval                                             | OpenAPI-derived SDK, React Query hooks, Zod schemas        |
| Unit tests           | Pytest / Vitest / Testing Library                 | Backend and frontend tests                                 |
| E2E                  | Playwright                                        | Browser smoke and provisioned flows                        |
| Observability        | Prometheus, OpenTelemetry, Grafana, Tempo, Sentry | Metrics, traces, dashboards, error monitoring              |
| Local infrastructure | Docker Compose                                    | PostgreSQL, Redis, Mailpit, MinIO definitions              |

## Capability Profiles

Capability profiles are deterministic starter slices built on the module-manifest graph. `CAPABILITY_PROFILE` can explicitly select a profile; otherwise bootstrap uses `PLATFORM_DEFAULT_MODULE_PACK`, whose example default is `full_platform`.

| Profile            | Extends | Added capabilities                                 | Intended use                      |
| ------------------ | ------- | -------------------------------------------------- | --------------------------------- |
| `core`             | —       | No optional platform pack or AI/RAG specialists    | General application foundation    |
| `lean_saas`        | `core`  | Billing, API keys, feature flags                   | SaaS starter                      |
| `rag`              | `core`  | AI, RAG, jobs, diagnostics                         | Retrieval/knowledge application   |
| `agent`            | `rag`   | Chat, memory, developer diagnostics                | RAG-backed agent/chat application |
| `automation_suite` | `core`  | API keys, webhooks, feature flags, email templates | Workflow/integration product      |
| `client_portal`    | `core`  | Billing, feature flags, email templates            | Subscription/client portal        |
| `full_platform`    | `core`  | All optional modules plus AI/RAG/agent specialists | Full reference platform           |

Profiles control more than navigation. The resolver computes:

* active modules;
* backend router contributions;
* Celery queues and scheduled tasks;
* module settings prefixes and dependency health checks;
* required permissions and feature flags;
* frontend route and navigation contributions.

See [`docs/capability-profiles.md`](docs/capability-profiles.md) and [`docs/module-manifests.md`](docs/module-manifests.md).

## Repository Structure

```text
generic_app/
├── .github/workflows/          # Backend and frontend CI
├── backend/
│   ├── alembic/                # Schema migrations
│   ├── api/                    # FastAPI entry point, middleware, router registry, health
│   ├── core/                   # Configuration, security, logging, cache/storage foundations
│   ├── db/                     # SQLAlchemy session/base infrastructure
│   ├── modules/                # Feature modules + manifest registry
│   ├── observability/          # Backend metrics/tracing integration
│   ├── scripts/                # Backend utility scripts, including OpenAPI export
│   ├── tests/                  # Cross-module/backend tests
│   ├── tools/                  # generic-app scaffold generator
│   ├── workers/                # Celery app, tasks, outbox, worker readiness
│   ├── .env.example
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── e2e/                    # Playwright suites
│   ├── openapi/                # Committed FastAPI schema
│   ├── scripts/                # API generation/check and bundle-budget scripts
│   ├── src/
│   │   ├── api/                # Authenticated transport and API wrappers
│   │   ├── app/                # Router, providers, theme, design tokens
│   │   ├── components/         # Shared UI/guards/layout
│   │   ├── config/             # Query and runtime configuration
│   │   ├── features/           # Feature-colocated UI
│   │   ├── generated/          # Orval-generated SDK
│   │   └── test/               # Frontend test setup
│   ├── package.json
│   ├── playwright.config.ts
│   └── vite.config.ts
├── infra/                      # Docker Compose for PostgreSQL/Redis/Mailpit/MinIO
├── observability/              # Prometheus/Grafana/Tempo configuration and docs
├── docs/                       # Architecture notes, ADRs, feature docs, runbooks
├── scripts/                    # Repository-level tooling (`generic-app` wrapper)
├── AGENTS.md                   # Repository contribution conventions for AI tools
├── DESIGN.md                   # UI design reference
├── Makefile
├── Makefile.local
└── Procfile.dev
```

> **Current-source note:** several source files and architecture documents reference shared utilities under `backend/lib/`, but that directory is not present in the current `main` tree exposed by GitHub. See [Current Main-Branch Notes](#current-main-branch-notes).

## Prerequisites

For the verified toolchain you need:

* Python **3.12 or newer**.
* [`uv`](https://docs.astral.sh/uv/) for the backend environment and commands used by CI/tooling.
* Node.js and npm. CI currently uses **Node 22**; the repository does not declare a formal minimum Node version in `package.json`.
* PostgreSQL 16 with the **pgvector** extension available before running all migrations.
* Redis.
* S3-compatible object storage when storage/RAG features are active; MinIO is the local definition.
* GNU Make and Honcho for the `make local-dev` convenience flow.
* Docker + Docker Compose if using `infra/docker-compose.yml`.

For the host-managed observability flow, Prometheus, Grafana, Tempo, `systemctl`, and appropriate service permissions are also required. Observability can be disabled for local development.

## Current Main-Branch Notes

The current `main` branch contains several inconsistencies that are important for a truthful setup guide:

1. **`backend/lib/` is referenced but absent.** Current backend source imports modules such as `backend.lib.vector_search`, `backend.lib.app_cache`, `backend.lib.idempotency`, and `backend.lib.failure_injection`, while the GitHub tree does not currently contain `backend/lib/`. Restore/reconcile that shared-library directory before expecting the backend to boot successfully.
2. **The Compose PostgreSQL image is not pgvector-enabled.** `infra/docker-compose.yml` currently uses `postgres:16`, while the RAG migrations/schema require the `vector` extension. Backend CI uses `pgvector/pgvector:pg16`. Use a pgvector-enabled PostgreSQL instance before applying the full migration chain.
3. **Environment examples require alignment.** `infra/.env.example` uses a non-`app` PostgreSQL password and MinIO credentials, while `backend/.env.example` contains different database/storage values. Make the backend URLs/credentials match the infrastructure values you actually start.
4. **The example JWT secret is intentionally unusable.** Backend validation rejects `JWT_SECRET=replace-me` and requires a high-entropy secret of at least 32 characters.
5. **Two root Make targets are stale.** `Makefile` delegates `docker-dev` and `prod-dev` to `Makefile.docker` and `Makefile.deploy`, but those files are not currently present. They are therefore not documented here as supported workflows.
6. **Grafana defaults are inconsistent across local files.** `Makefile.local` defaults to port `3000`, while `backend/.env.example` and `observability/README.md` point application links to `3001`. Set `GRAFANA_PUBLIC_URL` to the port used by your installation.

These notes should be removed or revised as the corresponding repository issues are fixed.

## Quick Start

The commands below describe the repository's verified development workflow. Resolve the current-branch notes above first, especially the missing shared-library path and pgvector requirement.

### 1. Clone

```bash
git clone https://github.com/oplt/generic_app.git
cd generic_app
```

### 2. Create environment files

```bash
cp infra/.env.example infra/.env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Before starting the backend, edit `backend/.env` so the infrastructure credentials match `infra/.env`.

With the checked-in local infrastructure examples, the corresponding database/storage values are:

```env
DATABASE_URL=postgresql+asyncpg://app:change-this-local-db-password@localhost:5432/app_db
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=change-this-local-minio-password
```

Generate a development JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `JWT_SECRET` in `backend/.env`.

### 3. Start infrastructure

The repository defines Redis, Mailpit, and MinIO directly in `infra/docker-compose.yml`:

```bash
docker compose -f infra/docker-compose.yml up -d redis mailpit minio
```

Provision PostgreSQL 16 separately with pgvector installed, or change the local Compose PostgreSQL image to a pgvector-enabled PostgreSQL 16 image before starting it. The backend CI uses `pgvector/pgvector:pg16`.

After PostgreSQL is available on the `DATABASE_URL` configured in `backend/.env`, continue with the backend setup.

### 4. Install backend dependencies and migrate

```bash
cd backend
uv sync --group dev
uv run alembic upgrade head
cd ..
```

### 5. Start the API

From the repository root:

```bash
PYTHONPATH=. uv run --project backend uvicorn backend.api.main:app --reload --port 8000
```

In non-production mode:

* API: `http://localhost:8000`
* Swagger UI: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`
* Liveness: `http://localhost:8000/health/live`
* Readiness: `http://localhost:8000/health/ready`

### 6. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to:

```text
http://localhost:5173
```

`frontend/.env.example` points API traffic at:

```text
http://localhost:8000/api/v1
```

### 7. Background workers

`backend/.env.example` sets `CELERY_TASK_ALWAYS_EAGER=true` for local development. Some task paths therefore execute without a separate production-style worker.

To exercise real queues, set:

```env
CELERY_TASK_ALWAYS_EAGER=false
```

Then start a worker from the repository root. For the default `full_platform` profile:

```bash
PYTHONPATH=. uv run --project backend celery \
  -A backend.workers.celery_app:celery_app worker \
  --loglevel=INFO \
  --queues=default,email,ingestion,cleanup,memory,evaluation,ai
```

Start Celery Beat as a separate process for scheduled/outbox dispatch work:

```bash
PYTHONPATH=. uv run --project backend celery \
  -A backend.workers.celery_app:celery_app beat \
  --loglevel=INFO
```

For another capability profile, consume the queues declared by that profile rather than automatically starting every specialist queue.

### Linux/Honcho convenience flow

`make local-dev` is a host-oriented convenience flow. It:

* validates local Python/Honcho/npm/Redis tools;
* cleans the application development ports;
* runs Alembic migrations;
* optionally starts Grafana, Prometheus, and Tempo through `systemd`;
* starts a Redis server on port `6380`;
* starts the FastAPI backend;
* starts a Celery worker for `default,email`;
* starts the Vite frontend;
* optionally opens the browser.

It does **not** provision PostgreSQL, MinIO, or Mailpit for you.

```bash
make local-dev
```

Without the host observability stack:

```bash
make local-dev-no-observability
```

## Local Services

The repository has two partially overlapping local workflows, so use the values that match the one you start.

| Service                  | Address / port                              | Source / note                                                            |
| ------------------------ | ------------------------------------------- | ------------------------------------------------------------------------ |
| Frontend                 | `http://localhost:5173`                     | Vite / `Makefile.local`                                                  |
| FastAPI                  | `http://localhost:8000`                     | Backend default                                                          |
| Swagger                  | `http://localhost:8000/docs`                | Development only                                                         |
| ReDoc                    | `http://localhost:8000/redoc`               | Development only                                                         |
| Health                   | `http://localhost:8000/health/live`         | Always-mounted health router                                             |
| PostgreSQL               | `localhost:5432`                            | `infra/docker-compose.yml`; must be pgvector-capable for full migrations |
| Redis (Compose)          | `localhost:6379`                            | `infra/docker-compose.yml`                                               |
| Redis (`make local-dev`) | `localhost:6380`                            | `Makefile.local` / `Procfile.dev`                                        |
| Mailpit SMTP             | `localhost:1025`                            | `infra/docker-compose.yml`                                               |
| Mailpit UI               | `http://localhost:8025`                     | `infra/docker-compose.yml`                                               |
| MinIO API                | `http://localhost:9000`                     | `infra/docker-compose.yml`                                               |
| MinIO console            | `http://localhost:9001`                     | `infra/docker-compose.yml`                                               |
| Prometheus               | `http://localhost:9090`                     | Host-managed observability                                               |
| Grafana                  | `http://localhost:3000` by `Makefile.local` | Set `GRAFANA_PUBLIC_URL` accordingly                                     |
| Tempo API                | `http://localhost:3200`                     | Host-managed observability                                               |
| OTLP gRPC                | `localhost:4317`                            | Tempo / OpenTelemetry                                                    |
| OTLP HTTP                | `http://localhost:4318`                     | Tempo / OpenTelemetry                                                    |

## Configuration

Backend settings are loaded from `backend/.env`. Frontend configuration is Vite-based and currently exposes `VITE_API_BASE`.

Use the example files as a catalog, not as production secrets:

* `backend/.env.example`
* `frontend/.env.example`
* `infra/.env.example`

### Core configuration

| Variable                       | Purpose                              | Required / default      |
| ------------------------------ | ------------------------------------ | ----------------------- |
| `APP_ENV`                      | Runtime environment                  | `dev` in example        |
| `APP_NAME`                     | FastAPI/platform application name    | `fullstack-app`         |
| `APP_VERSION`                  | Reported application version         | `0.1.0`                 |
| `DATABASE_URL`                 | Async PostgreSQL URL                 | Required                |
| `REDIS_URL`                    | Cache/rate-limit/Celery fallback URL | Required                |
| `PLATFORM_DEFAULT_MODULE_PACK` | Default capability profile           | `full_platform`         |
| `CAPABILITY_PROFILE`           | Explicit bootstrap profile override  | Empty by default        |
| `FRONTEND_URL`                 | Browser origin / auth links          | `http://localhost:5173` |
| `CORS_ALLOWED_ORIGINS`         | Allowed browser origins              | Frontend URL when empty |

### Authentication and email

| Variable                      | Purpose                                   | Example/default                        |
| ----------------------------- | ----------------------------------------- | -------------------------------------- |
| `JWT_SECRET`                  | JWT signing secret                        | Must be replaced; minimum 32 chars     |
| `JWT_ALGORITHM`               | JWT algorithm                             | `HS256`                                |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime                     | `15`                                   |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | Refresh-session lifetime                  | `7`                                    |
| `COOKIE_SECURE`               | Secure auth cookies                       | `false` in dev; required in production |
| `COOKIE_SAMESITE`             | SameSite policy                           | `lax`                                  |
| `REQUIRE_EMAIL_VERIFICATION`  | Enforce verified accounts                 | `true`                                 |
| `ADMIN_SIGNUP_INVITE_CODE`    | Invite-only admin elevation during signup | Empty                                  |
| `SMTP_HOST` / `SMTP_PORT`     | SMTP target                               | `localhost:1025` in example            |

### Celery

| Variable                    | Purpose                          | Example/default                            |
| --------------------------- | -------------------------------- | ------------------------------------------ |
| `CELERY_BROKER_URL`         | Broker override                  | Empty → `REDIS_URL`                        |
| `CELERY_RESULT_BACKEND`     | Result-backend override          | Empty → `REDIS_URL`                        |
| `CELERY_TASK_ALWAYS_EAGER`  | Development in-process execution | `true` in example; forbidden in production |
| `CELERY_TASK_DEFAULT_QUEUE` | Default queue                    | `default`                                  |
| `CELERY_EMAIL_QUEUE`        | Email queue                      | `email`                                    |
| `CELERY_INGESTION_QUEUE`    | RAG ingestion                    | `ingestion`                                |
| `CELERY_CLEANUP_QUEUE`      | Maintenance                      | `cleanup`                                  |
| `CELERY_MEMORY_QUEUE`       | Memory extraction                | `memory`                                   |
| `CELERY_EVALUATION_QUEUE`   | Evaluation work                  | `evaluation`                               |
| `CELERY_AI_QUEUE`           | AI generation                    | `ai`                                       |

### Object storage

| Variable                             | Purpose                | Example/default                     |
| ------------------------------------ | ---------------------- | ----------------------------------- |
| `STORAGE_BUCKET`                     | S3-compatible bucket   | `app-assets`                        |
| `STORAGE_ENDPOINT_URL`               | S3/MinIO endpoint      | `http://localhost:9000`             |
| `STORAGE_ACCESS_KEY`                 | Storage credential     | Must match local/production storage |
| `STORAGE_SECRET_KEY`                 | Storage secret         | Must match local/production storage |
| `STORAGE_PUBLIC_READ`                | Public bucket behavior | `false`                             |
| `STORAGE_SIGNED_URL_EXPIRES_SECONDS` | Signed URL lifetime    | `3600`                              |

### AI, chat, memory, and RAG

| Variable                   | Purpose                                            | Example/default       |
| -------------------------- | -------------------------------------------------- | --------------------- |
| `AI_DEFAULT_PROVIDER`      | Generation provider                                | Code default `local`  |
| `AI_EMBEDDING_PROVIDER`    | Embedding provider                                 | Code default `local`  |
| `OPENAI_API_KEY`           | Enables OpenAI adapter                             | Empty                 |
| `ANTHROPIC_API_KEY`        | Enables Anthropic generation adapter               | Empty                 |
| `CHAT_ENABLED`             | Enables chat rollout                               | `false`               |
| `WEB_SEARCH_ENABLED`       | Enables configured generic JSON web-search adapter | `false`               |
| `MEMORY_ENABLED`           | Enables memory layer                               | `true`                |
| `MEM0_MODE`                | Mem0 mode                                          | `hosted`              |
| `RAG_ENABLED`              | Enables RAG runtime checks                         | `true`                |
| `RAG_VECTOR_BACKEND`       | Vector backend                                     | `pgvector` only       |
| `RAG_EMBEDDING_DIMENSIONS` | Vector dimension                                   | `1536`                |
| `RAG_RETRIEVAL_STRATEGY`   | Retrieval mode                                     | `hybrid_rrf`          |
| `RAG_TOP_K`                | Final retrieval count                              | `5`                   |
| `RAG_ALLOWED_FILE_TYPES`   | Upload formats                                     | `pdf,txt,md,docx,csv` |
| `RAG_MAX_FILE_BYTES`       | Upload limit                                       | `10485760`            |

### Observability

| Variable                      | Purpose                     | Example/default                    |
| ----------------------------- | --------------------------- | ---------------------------------- |
| `SENTRY_DSN`                  | Optional Sentry integration | Empty                              |
| `OTEL_SERVICE_NAME`           | Trace service name          | `fastapi-backend`                  |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint               | `http://localhost:4318` in example |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | OTLP transport              | `http/protobuf`                    |
| `GRAFANA_PUBLIC_URL`          | Frontend/admin Grafana link | Align with local install           |
| `PROMETHEUS_PUBLIC_URL`       | Prometheus link             | `http://localhost:9090`            |
| `TEMPO_PUBLIC_URL`            | Tempo link                  | `http://localhost:3200`            |

The backend defines many additional cache TTLs, database pool limits, retry bounds, idempotency leases, diagnostics flags, and RAG quality controls. Consult `backend/.env.example` and the relevant focused docs before changing them.

## Authentication and Security

The implemented authentication flow is cookie-based from the browser's perspective:

1. A successful sign-in creates a database-backed refresh session.
2. The backend issues a short-lived signed JWT access token containing the user and session identifiers.
3. Access and refresh tokens are written to `httpOnly` cookies.
4. A separate readable CSRF cookie is paired with the configured CSRF request header on unsafe requests.
5. The frontend API client sends credentials, adds the CSRF header, and performs a single-flight access-token refresh after a `401` before declaring the browser session expired.
6. Refresh tokens are random values stored server-side only as hashes and are rotated on refresh.

Additional implemented controls include:

* Argon2 password hashing through Passlib.
* Email-verification tokens stored through Redis with expiration.
* Password-reset token flows that avoid revealing whether an email exists.
* Login/signup-related rate limiting.
* Optional admin signup through a configured invite code.
* TOTP MFA through `pyotp` for users with MFA enabled.
* Security-header middleware.
* CORS allow-listing.
* Production validation requiring secure cookies and HTTPS browser origins.
* Production rejection of eager Celery execution and failure-injection mode.

Swagger and ReDoc are disabled automatically when `APP_ENV=production`.

## Authorization and RBAC

Authentication establishes the actor; `backend/modules/policy/` handles capability authorization.

The policy catalog defines stable permission keys such as `project.read`, `rag.manage`, and `admin.manage`. Built-in roles include:

* `system_admin`
* `org_admin`
* `org_member`
* `project_editor`

Effective grants combine the bootstrap `users.is_admin` flag, explicit system/organization/project role assignments, and scoped organization-membership roles. Organization/project grants are designed not to cross tenant boundaries.

Representative policy APIs include:

```text
GET    /api/v1/policy/roles
GET    /api/v1/policy/permissions
POST   /api/v1/policy/role-assignments
DELETE /api/v1/policy/role-assignments
GET    /api/v1/policy/me/permissions
GET    /api/v1/policy/users/{id}/role-assignments
```

See [`docs/policy-rbac.md`](docs/policy-rbac.md).

## Application Modules

The module registry is explicit. It does not scan the filesystem or execute third-party modules dynamically.

### Registered application modules

| Module                  | Responsibility                                                    |
| ----------------------- | ----------------------------------------------------------------- |
| `storage`               | S3-compatible storage integration and health dependency           |
| `identity_access`       | Authentication, sessions, email verification, password reset, MFA |
| `users`                 | User-facing/admin user operations                                 |
| `profile`               | Profile operations                                                |
| `projects`              | Project domain and organization-aware project access              |
| `settings`              | Application/admin settings                                        |
| `platform`              | Platform metadata, profiles/packs, optional capabilities          |
| `policy`                | Capability authorization and role assignments                     |
| `observability`         | Operational status/links and backend observability integration    |
| `notifications`         | Notification functionality                                        |
| `calendar`              | Calendar feature/API                                              |
| `admin`                 | Administrative API/UI support                                     |
| `jobs`                  | Operational job console and job actions                           |
| `diagnostics`           | Infrastructure/application diagnostics                            |
| `developer_diagnostics` | Flag/profile-gated developer request diagnostics                  |
| `ai`                    | Prompt operations, providers, reviews, and evaluations            |
| `rag`                   | Document ingestion, retrieval, and knowledge grounding            |
| `chat`                  | Document-grounded knowledge chat                                  |
| `memory`                | Agent/user memory integration                                     |

### Optional platform modules

| Module            | Description                                          |
| ----------------- | ---------------------------------------------------- |
| `billing`         | Plan catalog and subscription management             |
| `api_keys`        | User-managed credentials for integrations/automation |
| `webhooks`        | Outbound event delivery                              |
| `feature_flags`   | Runtime rollout controls                             |
| `email_templates` | Customizable transactional email content             |

Module manifests can declare dependencies, routers, queues, scheduled tasks, settings prefixes, health checks, permissions, database requirements, feature flags, frontend routes, and navigation contributions.

## Module Generator

The scaffold generator follows the repository's modular-monolith conventions and patches only stable marker sections.

From the repository root:

```bash
./scripts/generic-app create-module --help
```

Example CRUD + UI + authorization + worker module:

```bash
./scripts/generic-app create-module orders \
  --crud \
  --frontend \
  --permissions \
  --celery \
  --optional
```

Example specialist attached to the RAG profile:

```bash
./scripts/generic-app create-module inventory \
  --crud \
  --frontend \
  --profile rag
```

The generator can create/wire:

* SQLAlchemy model, repository, service, schemas, CRUD router, Alembic revision, and tests;
* frontend feature and route/navigation registration;
* `{module}.read` / `{module}.manage` permission constants and route guards;
* Celery task module, queue contribution, and routing;
* outbox-ready event helper;
* storage dependency/health declarations;
* optional, core, or profile-selected module manifests.

Generation is designed to be deterministic and atomic: wiring failures roll back created/patched files.

See [`docs/module-generator.md`](docs/module-generator.md).

## AI and RAG Architecture

### AI providers

The provider registry currently contains:

* `local` — deterministic heuristic generation plus hash-derived local embeddings, intended for development/test behavior rather than model-quality generation;
* `openai` — chat-completions generation and embeddings through configured OpenAI-compatible base URLs;
* `anthropic` — message generation; embeddings are not implemented through Anthropic and must use the configured local embedding path instead.

Provider calls share timeout/retry infrastructure, and external providers require their corresponding API keys.

### RAG pipeline

```mermaid
flowchart LR
    Upload[Upload document]
    Validate[Validate / optional scan]
    Store[Object storage]
    Persist[Document + ingestion job + outbox]
    Dispatch[Celery Beat outbox dispatch]
    Worker[Ingestion worker]
    Parse[Parse]
    Chunk[Chunk]
    Embed[Embed]
    PG[(PostgreSQL + pgvector)]

    Query[User query]
    Vector[pgvector ANN]
    Lexical[PostgreSQL FTS]
    Fuse[RRF]
    Rerank[Optional reranker]
    Context[Bounded RAG + memory context]
    Generate[Generation provider]
    Cite[Citation validation / answer]

    Upload --> Validate --> Store --> Persist --> Dispatch --> Worker --> Parse --> Chunk --> Embed --> PG
    Query --> Vector
    Query --> Lexical
    PG --> Vector
    PG --> Lexical
    Vector --> Fuse
    Lexical --> Fuse
    Fuse --> Rerank --> Context --> Generate --> Cite
```

The upload path stores the document and records the ingestion intent in the same database transaction through the background-job outbox. Celery Beat claims outbox records and publishes the indexing task. The worker parses, chunks, embeds, and writes `rag_chunks` plus vector data.

Retrieval supports three strategies:

| Strategy     | Embedding | Candidate lanes | Fusion                 |
| ------------ | --------- | --------------- | ---------------------- |
| `vector`     | Yes       | pgvector ANN    | —                      |
| `lexical`    | No        | PostgreSQL FTS  | —                      |
| `hybrid_rrf` | Yes       | ANN + FTS       | Reciprocal Rank Fusion |

The lexical lane uses a stored `tsvector` and GIN index. The vector lane uses the pgvector cosine/HNSW path. Both lanes share user/organization/project/document filters before final results are assembled. An optional local reranker can run after candidate generation/fusion.

### RAG API

Representative routes:

```text
POST   /api/v1/rag/documents/upload
GET    /api/v1/rag/documents
GET    /api/v1/rag/documents/{id}
DELETE /api/v1/rag/documents/{id}
POST   /api/v1/rag/documents/{id}/index
GET    /api/v1/rag/documents/{id}/chunks
POST   /api/v1/rag/retrieve
POST   /api/v1/rag/ask
GET    /api/v1/rag/queries
GET    /api/v1/rag/jobs/{id}
POST   /api/v1/rag/jobs/{id}/retry
```

The `/api/v1/ai/documents*` compatibility surface delegates to the RAG document service when RAG is enabled so the application does not maintain a second ingestion corpus.

### Index versions and evaluation

The RAG stack includes:

* pipeline/index metadata for stale-document detection;
* building/activation/retention/rollback workflows for index versions;
* an admin evaluation workbench at `/admin/rag/evaluation`;
* golden datasets and cases;
* retrieval runs with Recall@K, Precision@K, MRR, and nDCG@K;
* per-candidate vector/lexical/fused scores;
* baseline comparisons and JSON/CSV export;
* optional heuristic answer-quality judgments without requiring LLM-as-judge.

For deeper detail, start with:

* [`backend/modules/rag/README.md`](backend/modules/rag/README.md)
* [`docs/hybrid-search.md`](docs/hybrid-search.md)
* [`docs/rag-index-versions.md`](docs/rag-index-versions.md)
* [`docs/rag-quality.md`](docs/rag-quality.md)
* [`docs/rag-evaluation-workbench.md`](docs/rag-evaluation-workbench.md)

## Background Jobs

Celery configuration is derived from the active capability profile.

### Logical queues

| Queue        | Typical responsibility         |
| ------------ | ------------------------------ |
| `default`    | General/default work           |
| `email`      | Transactional email            |
| `ingestion`  | RAG indexing                   |
| `cleanup`    | RAG/chat retention and cleanup |
| `memory`     | Memory extraction              |
| `evaluation` | AI/RAG evaluation work         |
| `ai`         | AI generation work             |

### Scheduled work

Core Beat entries include:

* background outbox dispatch every 30 seconds;
* expired idempotency-record cleanup every 15 minutes.

When the corresponding modules are active, Beat also adds hourly chat-retention cleanup and retired-RAG-index cleanup.

The Celery app enables late acknowledgement, rejects tasks on worker loss, uses a prefetch multiplier of one, applies hard/soft task time limits, and uses UTC.

Production configuration must run real workers (`CELERY_TASK_ALWAYS_EAGER=false`). Eager execution is explicitly rejected when `APP_ENV=production`.

See:

* [`docs/runbooks/outbox-dispatch.md`](docs/runbooks/outbox-dispatch.md)
* [`docs/runbooks/application-job-lifecycle.md`](docs/runbooks/application-job-lifecycle.md)
* [`docs/jobs-console.md`](docs/jobs-console.md)

## Data and Storage

### PostgreSQL

The primary relational store contains application, tenancy, policy, job, AI, and RAG data. PostgreSQL full-text search is also used by the lexical RAG lane.

### pgvector

RAG retrieval uses pgvector only. The current schema fixes vector dimensions at 1536 and includes an HNSW cosine index. Changing embedding dimensions requires an intentional schema migration rather than an environment-only change.

### Redis

Redis is used by multiple cross-cutting subsystems, including application caching, expiring authentication/reset tokens, rate limiting, distributed coordination, and the Celery broker/result backend unless dedicated Celery URLs are supplied.

### S3-compatible storage

The object-storage abstraction uses Boto3 and supports S3-compatible endpoints. MinIO is the repository's local storage definition. Storage is used by features such as document ingestion and avatar/assets handling.

### Local persistence

`infra/docker-compose.yml` defines persistent volumes for PostgreSQL and MinIO:

```text
postgres_data
minio_data
```

## API

Application feature routes are composed under:

```text
/api/v1
```

Health routes are mounted separately under:

```text
/health
```

Representative endpoints include:

```text
POST /api/v1/auth/sign-in
GET  /api/v1/auth/me
POST /api/v1/rag/retrieve
GET  /api/v1/policy/me/permissions
GET  /health/live
GET  /health/ready
```

FastAPI exposes development-only interactive docs at `/docs` and `/redoc`. They are disabled when `APP_ENV=production`.

Which `/api/v1` routers are actually mounted depends on the active capability profile.

## Typed Frontend SDK

FastAPI's OpenAPI document is the frontend wire-contract source of truth. Orval generates request/response models, endpoint functions, React Query hooks, and Zod schemas into `frontend/src/generated/`.

Layout:

```text
frontend/openapi/openapi.json
frontend/orval.config.ts
frontend/src/generated/
├── endpoints/
├── models/
├── zod/
└── index.ts
```

Generate from `frontend/`:

```bash
npm run api:generate
```

Check for committed schema/client drift:

```bash
npm run api:check
```

Or from the repository root:

```bash
./frontend/scripts/api-generate.sh
```

Generated requests use a custom mutator that delegates to the shared authenticated frontend API client, preserving cookie credentials, CSRF headers, refresh handling, and errors/correlation metadata.

See [`docs/openapi-frontend-sdk.md`](docs/openapi-frontend-sdk.md).

## Frontend Architecture

`frontend/src/` combines application infrastructure with feature colocation:

* `app/` — providers, router, theme, design tokens;
* `api/` — authenticated transport and hand-written compatibility wrappers;
* `generated/` — OpenAPI-derived models/hooks;
* `features/` — UI grouped by domain/feature;
* `components/` — shared layout and route guards;
* `config/` — shared query/runtime configuration;
* `hooks/`, `types/`, `utils/` — shared client utilities.

The router lazy-loads feature views. `ProtectedRoute` handles authenticated/admin browser access, while `ModuleRouteGate` checks module/page availability so inactive capability profiles do not mount specialist pages such as AI Studio, Knowledge Chat, RAG admin screens, jobs, or diagnostics.

The frontend API client:

* uses `VITE_API_BASE` (`http://localhost:8000/api/v1` in the example);
* sends browser credentials;
* reads the CSRF cookie and adds `X-CSRF-Token`;
* retries one `401` through a single shared refresh operation;
* exposes correlation IDs through its typed error type;
* supports streamed requests and upload progress.

The Vite configuration also enables PWA generation with auto-update registration and explicit manual chunks for React, router, query, forms, and MUI dependencies.

## Design System

`DESIGN.md` is the repository's detailed visual reference. The implemented MUI theme translates the reference into application tokens rather than relying on page-specific styling.

Key implemented tokens include:

* primary electric blue `#3E6AE1`;
* light/dark surface variants;
* restrained 400/500 font weights;
* 4px interactive and 12px card radii;
* 330ms shared motion timing;
* light and dark MUI palette support;
* application-level design tokens under `frontend/src/app/designTokens.ts` and theme overrides under `frontend/src/app/theme.ts`.

Treat `DESIGN.md` as a design reference; use the actual theme/tokens as the implementation source of truth.

## Caching, Idempotency, and Concurrency

### Caching

The documented shared application-cache API provides:

* Redis-backed reads/writes;
* namespace-scoped keys;
* user/organization/project scopes;
* TTLs and negative caching;
* tag invalidation;
* corpus/user generation counters for retrieval invalidation;
* in-process + Redis-lock single-flight loading;
* fail-open cache semantics when Redis is unavailable;
* low-cardinality Prometheus metrics.

See [`docs/caching.md`](docs/caching.md).

### Idempotency

The HTTP idempotency framework supports mutating endpoints that opt in to `Idempotency-Key`:

* first request executes and stores its response;
* the same key/body replays the stored response;
* the same key with a different fingerprint returns a conflict;
* concurrent requests coordinate so only one runner performs the effect.

The repository separately uses a durable external-effect ledger for ambiguous side effects such as email delivery. Beat cleans expired idempotency records periodically.

See [`docs/idempotency.md`](docs/idempotency.md) and [`docs/runbooks/external-effect-idempotency.md`](docs/runbooks/external-effect-idempotency.md).

### Concurrency and backpressure

Shared documented helpers cover:

* bounded gather/map operations;
* operation timeouts;
* selective retries for idempotent work;
* exponential backoff and Retry-After handling;
* loop-local concurrency limiters for external providers/search.

The rules explicitly prohibit automatic retries for non-idempotent work.

See [`docs/concurrency.md`](docs/concurrency.md).

## Observability

The backend wires observability during FastAPI startup and exposes Prometheus instrumentation. The implementation includes:

* structured application logging;
* correlation/request IDs;
* request/workflow/job metrics;
* Prometheus scraping;
* OpenTelemetry FastAPI/SQLAlchemy tracing;
* OTLP HTTP/gRPC exporters;
* optional Sentry integration;
* worker readiness and queue/job metrics;
* authenticated observability links/status in the application UI.

### Local host-managed stack

The checked-in local Make flow expects Grafana, Prometheus, and Tempo as host services managed through `systemd`, not Docker Compose.

```bash
make observability-up
make observability-status
make observability-logs
make observability-down
```

The backend metrics endpoint is:

```text
http://localhost:8000/metrics
```

The application also includes an authenticated Observability page at:

```text
http://localhost:5173/observability
```

See [`observability/README.md`](observability/README.md). Be aware of the Grafana port mismatch described in [Current Main-Branch Notes](#current-main-branch-notes).

## Diagnostics and Failure Injection

### Infrastructure diagnostics

The admin diagnostics surface is:

```text
UI:  /admin/diagnostics
API: GET /api/v1/admin/diagnostics
```

It summarizes application version/modules, PostgreSQL/pool/migrations/pgvector, Redis/cache, workers/queues, object storage, configured AI providers, and RAG status without exposing credentials or secret payloads.

See [`docs/diagnostics.md`](docs/diagnostics.md).

### Developer diagnostics

Developer diagnostics are separately flag/profile gated and intended for request-level debugging. See [`docs/developer-diagnostics.md`](docs/developer-diagnostics.md).

### Failure injection

Controlled dependency faults are **local/test only** and disabled by default:

```env
FAILURE_INJECTION_ENABLED=false
```

Production configuration rejects enabling failure injection. The harness can simulate PostgreSQL, Redis, AI-provider, storage, Celery, RAG, and SMTP failure modes to verify degraded behavior and idempotency.

See [`docs/failure-injection.md`](docs/failure-injection.md).

## Testing

### Backend

Install dependencies:

```bash
uv sync --project backend --group dev
```

Run the same broad pytest scope used by backend CI:

```bash
PYTHONPATH=. uv run --project backend pytest -q backend/tests backend/modules
```

Run the RAG module tests only:

```bash
PYTHONPATH=. uv run --project backend pytest -q backend/modules/rag/tests
```

Run the module-generator suite:

```bash
UV_CACHE_DIR=/tmp/generic-app-uv \
PYTHONPATH=. \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
uv run --project backend pytest backend/tools/generic_app/tests -q
```

### Frontend unit tests

```bash
cd frontend
npm ci
npm run test
```

Watch mode:

```bash
npm run test:watch
```

Coverage:

```bash
npm run test:coverage
```

### Frontend E2E

The default Playwright suite is a mocked Chromium smoke test and does not require backend credentials.

```bash
cd frontend
npm ci
npm run test:e2e:install
CI=1 npm run test:e2e
```

Install all supported Playwright browser binaries when needed:

```bash
npm run test:e2e:install:all
```

Credential-backed flows are intentionally separate:

```bash
npm run test:e2e:provisioned
```

Provisioned tests require the documented `E2E_*` environment configuration and running API/UI services; see [`frontend/README.md`](frontend/README.md).

### RAG offline evaluation

```bash
PYTHONPATH=. uv run --project backend python -m backend.modules.rag.evaluation \
  --json-output /tmp/rag-evaluation.json
```

## Code Quality

### Backend lint

Backend CI runs:

```bash
uv run --project backend ruff check backend
```

Ruff configuration is defined in `backend/pyproject.toml`.

### Frontend gates

```bash
cd frontend
npm run lint
npm run test
npm run build
npm run check:budgets:unit
npm run check:budgets
npm run api:check
```

### Root convenience targets

The root Makefile also contains:

```bash
make fix
make check
make commit-ready
```

These currently invoke Ruff plus `npx biome` and TypeScript checks. The frontend package does not currently declare Biome in `package.json`, so the GitHub Actions commands above are the more authoritative reproducible quality gates.

`make install-hooks` delegates to `pre-commit install`; ensure `pre-commit` and repository hook configuration are available before relying on that convenience target.

## CI

GitHub Actions runs on pull requests and pushes to `main`.

### Backend integration workflow

`.github/workflows/backend-integration.yml` provisions:

* `pgvector/pgvector:pg16`;
* Redis 7 Alpine;
* MinIO object storage;
* Python 3.12;
* `uv`.

It then runs:

1. backend dependency sync including development tools;
2. Ruff;
3. an Alembic single-head assertion;
4. `alembic upgrade head`;
5. `alembic check` as an advisory/non-blocking drift check;
6. Pytest across `backend/tests` and `backend/modules`.

### Frontend workflow

`.github/workflows/frontend.yml` uses Node 22 and runs:

1. `npm ci`;
2. backend dependency installation for OpenAPI export;
3. OpenAPI/client drift check;
4. ESLint;
5. Vitest;
6. production build;
7. bundle/PWA budget tests;
8. Playwright Chromium installation;
9. mocked Chromium E2E smoke.

Budget and Playwright reports are uploaded on the relevant outcomes.

## Database Migrations

Alembic is configured under `backend/`.

Apply migrations:

```bash
cd backend
uv run alembic upgrade head
```

Inspect heads:

```bash
uv run alembic heads
```

Check model/database drift:

```bash
uv run alembic check
```

For a conventional hand-written schema change, create an autogeneration candidate and review the generated revision before committing it:

```bash
uv run alembic revision --autogenerate -m "describe schema change"
```

The module generator creates a migration revision automatically when `--crud` is used and resolves the current single Alembic head programmatically rather than guessing.

Do not make production schema changes outside the migration chain.

## Development Workflow

A typical change follows this sequence:

1. Select/understand the active capability profile.
2. Provision PostgreSQL/pgvector, Redis, and required storage/email dependencies.
3. Configure `backend/.env` and `frontend/.env`.
4. Apply Alembic migrations.
5. Start the API and frontend.
6. Start the profile-appropriate Celery workers/Beat when testing asynchronous behavior.
7. Make changes inside the owning module/feature rather than crossing router boundaries.
8. Add/update focused tests.
9. Regenerate the OpenAPI frontend SDK if API contracts changed.
10. Run backend/frontend quality gates and relevant E2E tests.

Repository conventions from `AGENTS.md` additionally require focused diffs, reuse of existing shared patterns, no committed secrets/`.env`/Redis dumps, and disclosure of AI assistance in pull-request descriptions.

## Adding a Feature

For a conventional full-stack feature, prefer the module generator:

```bash
./scripts/generic-app create-module orders \
  --crud \
  --frontend \
  --permissions \
  --celery \
  --optional
```

The resulting feature can span:

```text
backend/modules/orders/
frontend/src/features/orders/
backend/alembic/versions/
backend/modules/manifests/registry.py
backend/api/router_registry.py
backend/modules/policy/catalog.py
backend/modules/manifests/celery_contrib.py
frontend/src/app/router.tsx
```

When adding features manually:

* keep models/repositories/services/schemas/routes inside the owning backend module;
* expose cross-feature behavior through deliberate service/port abstractions rather than importing another module's router;
* add manifest dependencies instead of assuming another module is active;
* gate frontend routes through the module/profile metadata when the feature is not universal;
* use generated OpenAPI types/functions for new frontend API contracts;
* use existing cache/idempotency/concurrency infrastructure instead of adding parallel helpers;
* add an Alembic migration for schema changes;
* run the relevant module and integration tests.

## Documentation Index

| Topic                               | Document                                                                                                       |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Architecture snapshot               | [`docs/architecture/baseline.md`](docs/architecture/baseline.md)                                               |
| Modular monolith ADR                | [`docs/adr/0001-modular-monolith.md`](docs/adr/0001-modular-monolith.md)                                       |
| Celery/Redis jobs ADR               | [`docs/adr/0002-celery-redis-async-jobs.md`](docs/adr/0002-celery-redis-async-jobs.md)                         |
| Module dependency graph ADR         | [`docs/adr/0003-module-dependency-graph.md`](docs/adr/0003-module-dependency-graph.md)                         |
| Durable module/job boundaries ADR   | [`docs/adr/0003-modular-boundaries-and-durable-jobs.md`](docs/adr/0003-modular-boundaries-and-durable-jobs.md) |
| Tenant/organization source of truth | [`docs/adr/0004-tenant-organization-source-of-truth.md`](docs/adr/0004-tenant-organization-source-of-truth.md) |
| Capability profiles                 | [`docs/capability-profiles.md`](docs/capability-profiles.md)                                                   |
| Module manifests                    | [`docs/module-manifests.md`](docs/module-manifests.md)                                                         |
| Module generator                    | [`docs/module-generator.md`](docs/module-generator.md)                                                         |
| Policy / RBAC                       | [`docs/policy-rbac.md`](docs/policy-rbac.md)                                                                   |
| Typed frontend SDK                  | [`docs/openapi-frontend-sdk.md`](docs/openapi-frontend-sdk.md)                                                 |
| Frontend/API contract               | [`docs/frontend-api-contract.md`](docs/frontend-api-contract.md)                                               |
| Caching                             | [`docs/caching.md`](docs/caching.md)                                                                           |
| Idempotency                         | [`docs/idempotency.md`](docs/idempotency.md)                                                                   |
| Concurrency/backpressure            | [`docs/concurrency.md`](docs/concurrency.md)                                                                   |
| Database pool sizing                | [`docs/database-pool-capacity.md`](docs/database-pool-capacity.md)                                             |
| Transaction ownership               | [`docs/transaction-ownership.md`](docs/transaction-ownership.md)                                               |
| Hybrid RAG search                   | [`docs/hybrid-search.md`](docs/hybrid-search.md)                                                               |
| RAG index versions                  | [`docs/rag-index-versions.md`](docs/rag-index-versions.md)                                                     |
| RAG quality strategies              | [`docs/rag-quality.md`](docs/rag-quality.md)                                                                   |
| RAG evaluation workbench            | [`docs/rag-evaluation-workbench.md`](docs/rag-evaluation-workbench.md)                                         |
| Jobs console                        | [`docs/jobs-console.md`](docs/jobs-console.md)                                                                 |
| Infrastructure diagnostics          | [`docs/diagnostics.md`](docs/diagnostics.md)                                                                   |
| Developer diagnostics               | [`docs/developer-diagnostics.md`](docs/developer-diagnostics.md)                                               |
| Failure injection                   | [`docs/failure-injection.md`](docs/failure-injection.md)                                                       |
| Cross-feature integration           | [`docs/cross-feature-integration.md`](docs/cross-feature-integration.md)                                       |
| Acceptance baselines                | [`docs/acceptance-baselines.md`](docs/acceptance-baselines.md)                                                 |
| AI/RAG degraded mode                | [`docs/runbooks/ai-rag-degraded-mode.md`](docs/runbooks/ai-rag-degraded-mode.md)                               |
| Dependency degradation              | [`docs/runbooks/dependency-degradation.md`](docs/runbooks/dependency-degradation.md)                           |
| Job lifecycle                       | [`docs/runbooks/application-job-lifecycle.md`](docs/runbooks/application-job-lifecycle.md)                     |
| Outbox dispatch                     | [`docs/runbooks/outbox-dispatch.md`](docs/runbooks/outbox-dispatch.md)                                         |
| External-effect idempotency         | [`docs/runbooks/external-effect-idempotency.md`](docs/runbooks/external-effect-idempotency.md)                 |
| Filtered HNSW recall                | [`docs/runbooks/filtered-hnsw-recall.md`](docs/runbooks/filtered-hnsw-recall.md)                               |
| Upload reconciliation               | [`docs/runbooks/document-upload-reconciliation.md`](docs/runbooks/document-upload-reconciliation.md)           |
| RAG dedup migration                 | [`docs/runbooks/rag-deduplication-migration.md`](docs/runbooks/rag-deduplication-migration.md)                 |
| Tenant integrity migration          | [`docs/runbooks/tenant-integrity-migration.md`](docs/runbooks/tenant-integrity-migration.md)                   |
| Local observability                 | [`observability/README.md`](observability/README.md)                                                           |
| RAG module                          | [`backend/modules/rag/README.md`](backend/modules/rag/README.md)                                               |
| Frontend testing/tooling            | [`frontend/README.md`](frontend/README.md)                                                                     |

## Troubleshooting

### Backend fails immediately with `ModuleNotFoundError: backend.lib...`

The current `main` tree references `backend.lib.*` from multiple backend files, while `backend/lib/` is currently absent. Restore/reconcile that shared-library package before debugging downstream services.

### Alembic fails while creating the `vector` extension

The current Compose file uses plain `postgres:16`, but RAG migrations require pgvector. Use PostgreSQL 16 with pgvector installed. Backend CI uses `pgvector/pgvector:pg16`.

### Backend rejects `JWT_SECRET`

`replace-me` is intentionally rejected. Generate a high-entropy secret with at least 32 characters and place it in `backend/.env`.

### Database authentication fails

Make `backend/.env`'s `DATABASE_URL` match `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in `infra/.env`. The two checked-in example files currently use different password values.

### MinIO requests fail with access-denied errors

Make `STORAGE_ACCESS_KEY` and `STORAGE_SECRET_KEY` in `backend/.env` match `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` in `infra/.env` for local MinIO.

### Redis connection fails

Check which local flow you are using:

* Docker Compose exposes Redis on `6379`.
* `make local-dev` starts/uses Redis on `6380`.

Ensure `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` point to the same intended instance.

### Celery tasks stay queued

* Confirm `CELERY_TASK_ALWAYS_EAGER=false` when testing real workers.
* Start a worker consuming the logical queue used by the active profile/task.
* Run Celery Beat for outbox-dispatched work.
* Check `/health/ready`, `/admin/jobs`, and `/admin/diagnostics` when available.

### OpenAPI client drift fails CI

Regenerate and inspect the generated diff:

```bash
cd frontend
npm run api:generate
npm run api:check
```

Commit intentional OpenAPI/schema/client changes together.

### Grafana links open the wrong port

`Makefile.local` currently defaults Grafana to `3000`, while another local example uses `3001`. Set `GRAFANA_PUBLIC_URL` to the address actually used by your Grafana service.

### A specialist page or API route is missing

Check the active capability profile. Routes, navigation, queues, and specialist modules are deliberately profile-gated.

### Development ports are already in use

The local Makefile includes diagnostics:

```bash
make -f Makefile.local list-ports
make -f Makefile.local check-ports
```

The `force-kill-ports` target uses `sudo` and can terminate unrelated/system services on the configured ports; use it deliberately.

## Production Considerations

This repository provides production-oriented application mechanisms, but the current `main` branch does **not** contain the `Makefile.deploy` referenced by the stale `prod-dev` target. Treat production deployment topology as an integration decision rather than assuming a supported one-command deployment.

At minimum, a production deployment should account for:

* a high-entropy `JWT_SECRET` and external secret management;
* HTTPS and `COOKIE_SECURE=true`;
* HTTPS frontend/CORS origins;
* managed or hardened PostgreSQL with pgvector when RAG migrations are present;
* connection-pool sizing against PostgreSQL limits;
* Redis authentication/network isolation/durability appropriate to its cache + broker roles;
* external S3-compatible object storage and private-bucket defaults;
* `CELERY_TASK_ALWAYS_EAGER=false`;
* separate API, profile-appropriate worker, and Celery Beat processes;
* Alembic migrations during controlled releases;
* production SMTP rather than Mailpit;
* observability endpoint/network access controls;
* configured OpenTelemetry/Sentry policy as required;
* keeping developer diagnostics restricted and failure injection disabled;
* health/readiness exposure settings appropriate to the deployment;
* explicit AI provider keys, quotas, timeouts, and data-handling policy where external providers are enabled.

Mailpit and the local MinIO setup are development conveniences, not production recommendations.

## Security Notes

* Never commit `.env` files, credentials, access tokens, API keys, cookies, or Redis dumps.
* Replace all local/example credentials before any shared or internet-accessible deployment.
* Keep object storage private unless public access is an explicit product requirement.
* Restrict admin, diagnostics, metrics, Grafana, Prometheus, and trace tooling at the network/application layers appropriate to your environment.
* Review CORS, cookie domain/SameSite, and HTTPS settings whenever frontend/API origins change.
* Use capability permissions for backend authorization; browser route guards are not a substitute for server-side authorization.
* Keep failure injection disabled outside controlled development/test use.

No `SECURITY.md` is currently present, so this README does not invent a vulnerability-reporting address.

## Contributing

No standalone `CONTRIBUTING.md` is currently present. Follow the repository conventions in `AGENTS.md` and the surrounding module patterns:

1. Keep changes focused and inside the owning module/feature.
2. Do not bypass module boundaries by importing another feature's router.
3. Reuse existing shared abstractions rather than creating duplicate helpers.
4. Use Python type hints and async SQLAlchemy patterns consistent with existing code.
5. Add or update tests for changed behavior.
6. Regenerate the frontend SDK when the FastAPI contract changes.
7. Run the relevant backend/frontend quality gates before submitting.
8. Do not commit secrets, `.env` files, or Redis dumps.
9. Disclose AI assistance in pull-request descriptions, as required by `AGENTS.md`.
10. Do not fabricate test results or API behavior in documentation or PRs.

## License

No `LICENSE`, `LICENSE.md`, or `LICENSE.txt` is currently included in the repository. Public GitHub visibility does not by itself grant a software license; add an explicit license before treating the project as generally redistributable under defined terms.
