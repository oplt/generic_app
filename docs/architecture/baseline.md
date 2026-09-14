# Architecture baseline (Phase 0)

Snapshot of how `generic_app` works today, before platform-capability phases.
Key ADRs: [0001 modular monolith](../adr/0001-modular-monolith.md),
[0002 Celery/Redis jobs](../adr/0002-celery-redis-async-jobs.md),
[0003 module dependency graph](../adr/0003-module-dependency-graph.md),
[0004 tenant organization](../adr/0004-tenant-organization-source-of-truth.md).

## RAG flow

1. **Upload** — `POST /api/v1/rag/documents/upload` → `DocumentIngestionService`
   validates/scans, stores object via `FileStorageAdapter`, creates `rag_documents` +
   `rag_ingestion_jobs`, enqueues `background_job_outbox` in the same transaction.
2. **Dispatch** — Celery Beat `dispatch_outbox_task` claims outbox rows
   (`FOR UPDATE SKIP LOCKED` + lease token) and publishes `index_rag_document_task`
   on the `ingestion` queue.
3. **Index** — Worker parses → chunks → embeds (`EmbeddingService` with cache) →
   writes `rag_chunks` + pgvector embeddings (HNSW). Pipeline version metadata is
   persisted for stale detection.
4. **Retrieve** — `RetrievalService`: optional retrieval cache → vector ANN and/or
   independent lexical FTS lane → RRF / hybrid ranker → filters (user/org/project).
5. **Answer** — `PromptContextService` / `RagContextBuilder` assemble context →
   `RagAnswerService` via `GenerationPort` → `CitationService`.

Primary paths: `backend/modules/rag/api/`, `application/`, `infrastructure/`,
`backend/workers/outbox.py`, `backend/modules/rag/README.md`.

## Caching architecture

- Shared API: `backend/lib/app_cache/` (`get` / `set` / `delete` /
  `invalidate_tags` / `get_or_set`) — see [docs/caching.md](../caching.md).
- Redis (`REDIS_URL`) behind `backend/core/cache.py` with `ga:` key prefix.
- Process-local TTL cache for hot platform/settings/observability keys.
- Domain helpers: `backend/lib/retrieval_cache.py`, `embedding_cache.py`,
  `resource_cache.py`, `memory_search_cache.py` (retrieval/embedding use
  `app_cache`).
- Metrics: hit/miss/error/stale (core) plus writes/latency/negative/tags
  (app_cache); fail-open on Redis errors (treat as miss).
- Invalidation: corpus generation bumps for org/project; optional tag sets;
  settings/platform keys invalidate on admin writes.

## Authorization flow

- Short-lived JWT access cookie + rotating refresh session (`identity_access`).
- CSRF double-submit on unsafe methods (`backend/api/middleware/csrf.py`).
- `get_current_user` / `get_admin_user` dependencies.
- Tenant: organization is authoritative; projects carry `organization_id`
  (ADR 0004). `SqlAlchemyProjectAccessPort.resolve_ownership_scope` derives
  org from project (or explicit membership when no project).
- Assignment grants project read only within the project's organization.
- Admin gate is `User.is_admin` today (capability RBAC is a later phase).

## Celery architecture

- App: `backend/workers/celery_app.py` — queues `default`, `email`, `ingestion`,
  `cleanup`, `memory`, `evaluation`, `ai`.
- Beat: outbox every 30s; chat retention hourly; Redis NX + PG advisory locks
  prevent overlapping ticks (`schedule_lock.py`).
- Outbox + lease tokens: `docs/runbooks/outbox-dispatch.md`.
- Logical jobs: `application_jobs` via `job_service.run_tracked_sync` /
  `ensure_queued_job` — `docs/runbooks/application-job-lifecycle.md`.
- External effect ledger for ambiguous side effects.

## Module-pack architecture

- Catalog + packs: `backend/modules/platform/defaults.py` (`MODULE_CATALOG`
  derived from optional manifests; `MODULE_PACKS` derived from capability
  profiles: core, lean_saas, rag, agent, automation_suite, client_portal,
  full_platform).
- Runtime resolution: `PlatformConfigService` merges pack modules with DB
  overrides, then `effective_modules(...)` / `resolve_capability_profile(...)`;
  caches under `ga:platform:config`.
- Optional routers (billing, webhooks, feature flags, …) call
  `ensure_module_enabled` (checks `active_modules` ∪ `enabled_modules`).
- Frontend: `frontend/src/api/platform.ts`, platform-admin UI;
  `useModuleNavigation` reads `module_nav` / `active_modules`.

Declarative per-module manifests (`manifest.py`) are registered intentionally in
`backend/modules/manifests/registry.py` and validated at startup; packs/profiles
select optional modules. See [docs/module-manifests.md](../module-manifests.md)
and [docs/capability-profiles.md](../capability-profiles.md).

## React API / data-fetching

- Shared client: `frontend/src/api/client.ts` — cookie credentials, CSRF header,
  single-flight refresh on 401, stream/upload helpers.
- TanStack Query: `frontend/src/config/queryClient.ts`, `queryKeys.ts`.
- Feature colocation: `frontend/src/features/*` + thin `frontend/src/api/*`
  wrappers. Auth context owns session bootstrap.

## Observability architecture

- Logging: `backend/core/logging.py` (correlation IDs, redaction).
- Prometheus metrics: `backend/observability/prometheus_metrics.py` + module
  metrics; scrape via app middleware.
- OpenTelemetry + optional Sentry: `backend/observability/setup.py`.
- Health: `/health/live`, `/ready` (db/redis/queue/storage/vector +
  `dependency_states`), `/version` — `backend/api/v1/health.py`.
- Stack configs: `observability/`; admin UI links to Grafana/Tempo.

## Existing partial implementations vs planned phases

| Planned capability | Already present (reuse) | Gap |
| --- | --- | --- |
| Standardized cache | `lib/app_cache/` + `core/cache.py` | Broader module adoption beyond RAG |
| Concurrency utilities | `lib/concurrency.py` + provider/memory/RAG adoption | Broader worker/eval adoption |
| Idempotency | `lib/idempotency/` + effect ledger | Broader HTTP endpoint adoption |
| RBAC | `modules/policy/` + membership heuristics | Broader replacement of remaining `is_admin` checks |
| Module manifests | `modules/manifests/` + per-module `manifest.py` | Broader optional-module adoption |
| Capability profiles | `platform/profiles.py` + pack derivation | Broader worker/queue process binding |
| Module generator | `tools/generic_app/` + Jinja templates + pageKeys/pageRegistry wiring | Prefer generator; see [adding-a-feature.md](../adding-a-feature.md) |
| OpenAPI TS SDK | `frontend/src/generated/` via Orval | Broader replacement of hand-written `src/api/*` types |
| RAG index versions | `rag_index_versions` + admin UI | Multi-column vector storage for concurrent dim migrations |
| Hybrid search | independent ANN + FTS lanes, RRF, strategies | Quality loop via evaluation workbench |
| RAG evaluation workbench | datasets/cases/runs + admin UI + metrics | Broader generation-judge providers |
| Jobs console | `application_jobs` + RAG jobs admin UI | Broader retry dispatch for non-RAG families |
| RAG quality strategies | configurable dedup/MMR/neighbors/parent-child/rerankers | Promote defaults only after measured wins |
| Diagnostics | `/admin/diagnostics` + Prometheus reuse | Deeper Tempo deep-links per section |
| Developer diagnostics | flag-gated request panel + OTEL hooks | Persist recent requests beyond process memory |
| Failure injection | `lib/failure_injection` + resilience tests | Broader compose chaos scenarios |
| Cross-feature integration | manifests↔profiles↔RBAC↔jobs↔diagnostics↔RAG | Broader e2e acceptance automation |
