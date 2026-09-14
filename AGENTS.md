# AI Assistant Guidelines — generic_app

Guidelines for AI tools contributing to this fullstack monorepo (FastAPI + React).

## Architecture

- **Backend:** modular monolith under `backend/modules/` (`identity_access`, `users`, `projects`, `ai`, `rag`, `memory`, …)
- **Shared libs:** `backend/lib/` (vectors, caches, pagination), `backend/core/` (config, cache, storage)
- **Frontend:** React + Vite in `frontend/src/`; prefer `features/*` colocation for new UI
  (canonical views under `features/<feature>/views/` — no parallel `src/pages/` layer)
- **API modules:** routers live under `backend/modules/<key>/` and mount via
  `backend/api/router_registry.py` + manifests. `backend/api/v1/` is health-only.
  Each manifest declares an explicit `ModuleSurface` (`user_facing` / `admin_facing` /
  `embedded` / `api_only` / `internal`). Frontend pages register in
  `frontend/src/app/pageRegistry.ts` + `pageKeys.json` (trusted allow-list).
- **Observability:** `backend/observability/` + `observability/` (Grafana/Prometheus/Tempo configs)

## Adding a feature

Follow [docs/adding-a-feature.md](../docs/adding-a-feature.md). Prefer
`./scripts/generic-app create-module …` so registry / router / page-key seams are
patched via markers instead of ad-hoc edits.

## Conventions

- Python: type hints, async SQLAlchemy sessions, `HTTPException` for API errors
- RAG documents live in the `rag` module; `/api/v1/ai/documents*` delegates to `LegacyAiDocumentService` when `RAG_ENABLED=true`
- Do not reintroduce parallel AI document ingestion — use RAG ingestion only
- Vector search: pgvector only (`RAG_VECTOR_BACKEND=pgvector`); unsupported backends fail at startup
- Tests: `pytest` / `unittest` under `backend/tests/` and `backend/modules/*/tests/`
- Logging: centralized setup in `backend/core/logging.py`; see [docs/logging.md](../docs/logging.md)

## Before submitting changes

1. Run relevant tests (see `Makefile`, module READMEs)
2. Keep diffs focused; match existing patterns in the touched module
3. Disclose AI assistance in PR descriptions
4. Do not commit secrets, `.env`, or Redis dumps (`dump.rdb`)

## Do not

- Fabricate test results or API behavior
- Add duplicate helpers when `backend/lib/` already provides them
- Bypass module boundaries (e.g. import another module's `router.py` from feature code)
- Add feature routes under `backend/api/v1/` or recreate `frontend/src/pages/` re-exports
