# Generic App

Generic full-stack starter with:

- FastAPI backend
- React + Vite frontend
- PostgreSQL, Redis, and MinIO for local infrastructure
- Celery workers for asynchronous jobs, using Redis as broker/result backend
- JWT auth with refresh rotation
- Admin settings, notifications, profile, and project modules
- Optional platform modules for billing, API keys, webhooks, feature flags, and email templates
- Sentry/OpenTelemetry hooks and S3-compatible avatar storage

## Local Setup

1. Start infrastructure:

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up -d
```

Mailpit is included for local email capture:

- SMTP server: `localhost:1025`
- Web inbox: `http://localhost:8025`

2. Configure the backend:

```bash
cd backend
cp .env.example .env
uv sync
.venv/bin/alembic upgrade head
```

See [docs/caching.md](docs/caching.md) for the shared application cache API.
See [docs/concurrency.md](docs/concurrency.md) for bounded gather, retries, and backpressure helpers.
See [docs/idempotency.md](docs/idempotency.md) for HTTP Idempotency-Key and Celery effect helpers.
See [docs/policy-rbac.md](docs/policy-rbac.md) for capability permissions and role assignment.
See [docs/module-manifests.md](docs/module-manifests.md) for declarative module manifests and dependency validation.
See [docs/capability-profiles.md](docs/capability-profiles.md) for starter capability profiles (core, rag, agent, …).
See [docs/module-generator.md](docs/module-generator.md) for `generic-app create-module` scaffolding.
See [docs/openapi-frontend-sdk.md](docs/openapi-frontend-sdk.md) for the typed OpenAPI TypeScript client.
See [docs/rag-index-versions.md](docs/rag-index-versions.md) for versioned RAG indexes and stale reindex.
See [docs/hybrid-search.md](docs/hybrid-search.md) for vector + lexical + RRF retrieval.
See [docs/rag-evaluation-workbench.md](docs/rag-evaluation-workbench.md) for dataset runs and metrics.
See [docs/jobs-console.md](docs/jobs-console.md) for the admin jobs console.
See [docs/diagnostics.md](docs/diagnostics.md) and [docs/developer-diagnostics.md](docs/developer-diagnostics.md).
See [docs/failure-injection.md](docs/failure-injection.md) for controlled local/test faults.
See [docs/cross-feature-integration.md](docs/cross-feature-integration.md) for the Phase 17 wiring map.
See [docs/logging.md](docs/logging.md) for log file location, rotation, and correlation IDs.
See [docs/architecture/baseline.md](docs/architecture/baseline.md) for the Phase 0 architecture snapshot (RAG, cache, auth, Celery, module packs, frontend data fetching, observability).

3. Start the backend:

```bash
cd backend
.venv/bin/uvicorn backend.api.main:app --reload
```

4. Start the Celery worker:

```bash
cd backend
.venv/bin/celery -A backend.workers.celery_app:celery_app worker --loglevel=INFO --queues=default,email,ingestion,cleanup,memory,evaluation
```

Run the outbox scheduler as a separate production process:

```bash
.venv/bin/celery -A backend.workers.celery_app:celery_app beat --loglevel=INFO
```

5. Configure the frontend:

```bash
cd frontend
cp .env.example .env
npm install
```

6. Start the frontend:

```bash
cd frontend
npm run dev
```

Or start the full local development stack, including Prometheus, Grafana, and Tempo:

```bash
make local-dev
```

Observability setup and verification steps are documented in
[observability/README.md](observability/README.md).

## Notes

- Local object storage uses MinIO on `http://localhost:9000` and its console on `http://localhost:9001`.
- Local infrastructure secrets now come from `infra/.env`; the compose file no longer embeds credentials.
- Redis now serves both app-level caching/token storage and the Celery broker/result backend.
- Production background work crosses the Celery boundary: run workers for email, ingestion, cleanup, memory, and evaluation queues.
- Local `.env.example` defaults to Mailpit plus `CELERY_TASK_ALWAYS_EAGER=true`, so signup/reset emails work without a separate worker.
- Avatar uploads are stored in the configured S3-compatible bucket instead of a placeholder path.
- `/admin/platform` lets you rename the app, rename the core domain labels, pick a module pack, and manage plans, flags, and email templates.
- Set `ADMIN_SIGNUP_INVITE_CODE` in `backend/.env` to allow invite-only admin registration during sign-up.
- Authentication now uses `httpOnly` cookies plus a CSRF token cookie/header pair for state-changing requests.
- Module packs are intended for clone-time reuse:
  - `lean_saas`
  - `automation_suite`
  - `client_portal`
  - `full_platform`
- Observability is enabled through backend config:
  - `SENTRY_DSN`
  - `SENTRY_TRACES_SAMPLE_RATE`
  - `OTLP_ENDPOINT`
  - `OTLP_INSECURE`
  - `OTEL_SERVICE_NAME`
  - `OTEL_EXPORTER_OTLP_ENDPOINT`
  - `OTEL_EXPORTER_OTLP_PROTOCOL`
  - `OTEL_TRACES_EXPORTER`
  - `GRAFANA_PUBLIC_URL`
  - `PROMETHEUS_PUBLIC_URL`
  - `TEMPO_PUBLIC_URL`
