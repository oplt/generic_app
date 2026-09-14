"""Aggregate production-safe diagnostics from health probes and Prometheus gauges."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.v1.health import dependency_operational_state
from backend.core.cache import (
    cache_errors_total,
    cache_hits_total,
    cache_misses_total,
    redis_client,
)
from backend.core.config import settings
from backend.core.log_redaction import redact_url
from backend.core.storage import object_storage
from backend.db.session import POOL_LABEL, engine
from backend.lib.vector_search import pgvector_readiness
from backend.modules.ai.provider_service import AiProviderService
from backend.modules.diagnostics.schemas import (
    AiProviderDiagnostics,
    DiagnosticsResponse,
    DiagnosticsSection,
    OperationalState,
)
from backend.modules.platform.config_service import PlatformConfigService
from backend.modules.rag.application.index_version_service import IndexVersionService
from backend.modules.rag.infrastructure import metrics as rag_metrics
from backend.observability import prometheus_metrics
from backend.workers.celery_app import celery_app
from backend.workers.readiness import worker_readiness

_PROCESS_STARTED_AT = datetime.now(UTC)
_SECRET_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|credential|cookie|database_url)",
    re.I,
)


def _safe_host(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(redact_url(url))
    host = parts.hostname or parts.netloc
    if parts.port:
        return f"{host}:{parts.port}"
    return host or None


def _metric_samples(metric) -> list[Any]:
    samples: list[Any] = []
    try:
        for family in metric.collect():
            samples.extend(family.samples)
    except Exception:
        return []
    return samples


def _counter_sum(metric) -> float | None:
    total = 0.0
    found = False
    for sample in _metric_samples(metric):
        name = sample.name
        if name.endswith("_created") or name.endswith("_bucket") or name.endswith("_sum"):
            continue
        if name.endswith("_count") and not name.endswith("_total") and "_total" not in getattr(
            metric, "_name", ""
        ):
            # histogram counts — skip when summing counters
            continue
        total += float(sample.value)
        found = True
    return total if found else None


def _gauge_value(metric, **labels: str) -> float | None:
    try:
        if labels:
            return float(metric.labels(**labels)._value.get())
        return float(metric._value.get())
    except Exception:
        return None


def _histogram_avg(metric) -> float | None:
    total_sum = 0.0
    total_count = 0.0
    for sample in _metric_samples(metric):
        if sample.name.endswith("_sum"):
            total_sum += float(sample.value)
        elif sample.name.endswith("_count"):
            total_count += float(sample.value)
    if total_count <= 0:
        return None
    return total_sum / total_count


def _cache_hit_ratio() -> float | None:
    hits = _counter_sum(cache_hits_total) or 0.0
    misses = _counter_sum(cache_misses_total) or 0.0
    total = hits + misses
    if total <= 0:
        return None
    return hits / total


def _worst_state(states: list[OperationalState]) -> OperationalState:
    rank = {
        "healthy": 0,
        "not_required": 0,
        "unknown": 1,
        "degraded": 2,
        "unavailable": 3,
    }
    if not states:
        return "unknown"
    return max(states, key=lambda state: rank.get(state, 1))


def _assert_no_secrets(payload: dict[str, Any], *, path: str = "root") -> None:
    """Raise AssertionError when secret-shaped keys/values appear (tests + defensive)."""

    for key, value in payload.items():
        if _SECRET_KEY_RE.search(str(key)):
            raise AssertionError(f"Secret-shaped key at {path}.{key}")
        if isinstance(value, dict):
            _assert_no_secrets(value, path=f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    _assert_no_secrets(item, path=f"{path}.{key}[{index}]")
        elif isinstance(value, str):
            lowered = value.lower()
            if "password=" in lowered or "api_key=" in lowered:
                raise AssertionError(f"Secret-shaped value at {path}.{key}")


def _inspect_celery() -> tuple[dict, dict]:
    inspector = celery_app.control.inspect(timeout=0.5)
    return inspector.ping() or {}, inspector.active_queues() or {}


class DiagnosticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def collect(self) -> DiagnosticsResponse:
        (
            application,
            postgresql,
            redis_section,
            celery_section,
            storage,
            ai_providers,
            rag,
        ) = await asyncio.gather(
            self._application(),
            self._postgresql(),
            self._redis(),
            self._celery(),
            self._storage(),
            self._ai_providers(),
            self._rag(),
        )
        overall = _worst_state(
            [
                application.state,
                postgresql.state,
                redis_section.state,
                celery_section.state,
                storage.state,
                rag.state,
                *(provider.state for provider in ai_providers if provider.configured),
            ]
        )
        from backend.lib.failure_injection import active_faults, injection_permitted
        from backend.lib.failure_injection.runtime import operational_state_for_fault
        from backend.observability.service import build_public_url

        faults = sorted(active_faults())
        if faults:
            # Active injection should never report a fully healthy platform.
            overall = _worst_state(
                [overall, *(operational_state_for_fault(kind) for kind in faults)]  # type: ignore[list-item]
            )
            if overall == "healthy":
                overall = "degraded"

        grafana = build_public_url(settings.GRAFANA_PUBLIC_URL)
        tempo = build_public_url(
            settings.GRAFANA_PUBLIC_URL,
            settings.GRAFANA_TEMPO_EXPLORE_PATH,
        )
        response = DiagnosticsResponse(
            generated_at=datetime.now(UTC).isoformat(),
            overall_state=overall,
            application=application,
            postgresql=postgresql,
            redis=redis_section,
            celery=celery_section,
            storage=storage,
            ai_providers=ai_providers,
            rag=rag,
            observability_hints={
                "prometheus_metric_names": [
                    "db_pool_checked_out",
                    "db_pool_size",
                    "db_pool_overflow",
                    "worker_queue_depth",
                    "worker_failed_job_count",
                    "rag_embedding_latency_ms",
                    "rag_retrieval_latency_ms",
                    "cache_hits_total",
                    "cache_misses_total",
                ],
                "grafana_base_url": grafana,
                "tempo_explore_url": tempo,
                "observability_page": "/observability",
                "failure_injection": {
                    "permitted": injection_permitted(),
                    "env_enabled": bool(
                        getattr(settings, "FAILURE_INJECTION_ENABLED", False)
                    ),
                    "active_faults": faults,
                },
                "note": (
                    "Prefer Grafana/Tempo for deep latency analysis; this page reuses "
                    "gauges. Active failure-injection faults are listed when permitted."
                ),
            },
        )
        _assert_no_secrets(response.model_dump())
        return response

    async def _application(self) -> DiagnosticsSection:
        uptime = max(0.0, (datetime.now(UTC) - _PROCESS_STARTED_AT).total_seconds())
        active_modules: list[str] = []
        module_pack: str | None = None
        try:
            metadata = await PlatformConfigService(self.db).get_platform_metadata()
            active_modules = list(metadata.active_modules)
            module_pack = metadata.module_pack
        except Exception:
            active_modules = []
        return DiagnosticsSection(
            state="healthy",
            detail="Application process is serving diagnostics",
            metrics={
                "app_name": settings.APP_NAME,
                "environment": settings.APP_ENV,
                "version": settings.APP_VERSION,
                "git_commit": settings.GIT_COMMIT or None,
                "uptime_seconds": round(uptime, 1),
                "started_at": _PROCESS_STARTED_AT.isoformat(),
                "module_pack": module_pack,
                "enabled_modules": active_modules,
                "async_jobs": "celery",
            },
        )

    async def _postgresql(self) -> DiagnosticsSection:
        connectivity = "error"
        migration_revision: str | None = None
        latency_ms: float | None = None
        try:
            from backend.lib.failure_injection import maybe_inject
            from backend.lib.failure_injection.kinds import FaultKind

            maybe_inject(FaultKind.POSTGRES_CONNECTION)
            maybe_inject(FaultKind.POSTGRES_POOL_EXHAUSTED)
            maybe_inject(FaultKind.POSTGRES_SLOW_QUERY)
            started = time.perf_counter()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                revision = await conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                migration_revision = revision.scalar_one_or_none()
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            connectivity = "ok"
        except Exception as exc:
            detail = f"PostgreSQL connectivity failed ({type(exc).__name__})"
            return DiagnosticsSection(
                state="unavailable",
                detail=detail,
                metrics={
                    "connectivity": connectivity,
                    "pool": self._pool_metrics(),
                },
            )

        vector = await pgvector_readiness(self.db)
        vector_state = "healthy" if vector.available else (
            "not_required" if not settings.RAG_ENABLED else "unavailable"
        )
        state: OperationalState = "healthy"
        if not vector.available and settings.RAG_ENABLED:
            state = "degraded"
        return DiagnosticsSection(
            state=state,
            detail=(
                "PostgreSQL reachable"
                if state == "healthy"
                else "PostgreSQL up; pgvector not ready"
            ),
            metrics={
                "connectivity": connectivity,
                "latency_ms": latency_ms,
                "migration_revision": migration_revision,
                "pool": self._pool_metrics(),
                "pgvector": {
                    "state": vector_state,
                    "available": vector.available,
                    "reason": vector.reason,
                },
                "database_host": _safe_host(settings.DATABASE_URL),
            },
        )

    def _pool_metrics(self) -> dict[str, Any]:
        pool = engine.sync_engine.pool
        checked_out = pool.checkedout()
        size = pool.size()
        overflow = max(pool.overflow(), 0)
        return {
            "checked_out": checked_out,
            "size": size,
            "overflow": overflow,
            "configured_pool_size": settings.DB_POOL_SIZE,
            "configured_max_overflow": settings.DB_MAX_OVERFLOW,
            "configured_pool_timeout_seconds": settings.DB_POOL_TIMEOUT_SECONDS,
            "prometheus": {
                "checked_out": _gauge_value(
                    prometheus_metrics.db_pool_checked_out, pool=POOL_LABEL
                ),
                "size": _gauge_value(prometheus_metrics.db_pool_size, pool=POOL_LABEL),
                "overflow": _gauge_value(
                    prometheus_metrics.db_pool_overflow, pool=POOL_LABEL
                ),
            },
        }

    async def _redis(self) -> DiagnosticsSection:
        latency_ms: float | None = None
        memory_summary: dict[str, Any] = {}
        try:
            from backend.lib.failure_injection import maybe_inject
            from backend.lib.failure_injection.kinds import FaultKind

            maybe_inject(FaultKind.REDIS_UNAVAILABLE)
            maybe_inject(FaultKind.REDIS_TIMEOUT)
            started = time.perf_counter()
            await redis_client.ping()
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            try:
                info = await redis_client.info("memory")
                memory_summary = {
                    "used_memory_human": info.get("used_memory_human"),
                    "maxmemory_human": info.get("maxmemory_human"),
                    "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio"),
                }
            except Exception:
                memory_summary = {"available": False}
        except Exception as exc:
            return DiagnosticsSection(
                state="unavailable",
                detail=f"Redis connectivity failed ({type(exc).__name__})",
                metrics={
                    "connectivity": "error",
                    "cache_hit_ratio": _cache_hit_ratio(),
                    "cache_errors": _counter_sum(cache_errors_total),
                    "broker_host": _safe_host(settings.REDIS_URL),
                },
            )

        hit_ratio = _cache_hit_ratio()
        return DiagnosticsSection(
            state="healthy",
            detail="Redis reachable",
            metrics={
                "connectivity": "ok",
                "latency_ms": latency_ms,
                "memory": memory_summary,
                "cache_hit_ratio": hit_ratio,
                "cache_hits": _counter_sum(cache_hits_total),
                "cache_misses": _counter_sum(cache_misses_total),
                "cache_errors": _counter_sum(cache_errors_total),
                "celery_broker": "redis",
                "broker_host": _safe_host(settings.REDIS_URL),
            },
        )

    async def _celery(self) -> DiagnosticsSection:
        readiness = await worker_readiness()
        workers: list[str] = []
        queues: list[str] = []
        stale_workers: list[str] = []
        if not settings.CELERY_TASK_ALWAYS_EAGER:
            try:
                ping, active_queues = await asyncio.wait_for(
                    asyncio.to_thread(_inspect_celery), timeout=2.0
                )
                workers = sorted(ping.keys())
                observed = {
                    queue["name"]
                    for queue_list in active_queues.values()
                    if isinstance(queue_list, list)
                    for queue in queue_list
                    if isinstance(queue, dict) and queue.get("name")
                }
                queues = sorted(observed)
                # Workers that do not answer ping are treated as stale/missing.
                for name in active_queues:
                    if name not in ping:
                        stale_workers.append(name)
            except Exception:
                workers = []
                queues = []

        state = dependency_operational_state(readiness.status)
        if state not in {"healthy", "degraded", "unavailable", "not_required", "unknown"}:
            state = "unknown"
        typed_state: OperationalState = state  # type: ignore[assignment]
        return DiagnosticsSection(
            state=typed_state,
            detail=readiness.detail,
            metrics={
                "eager_mode": settings.CELERY_TASK_ALWAYS_EAGER,
                "workers": workers,
                "worker_count": len(workers),
                "queues": queues,
                "queue_depth": readiness.queue_depth,
                "oldest_job_age_seconds": readiness.oldest_job_age_seconds,
                "retry_count": readiness.retry_count,
                "failed_job_count": readiness.failed_job_count,
                "last_successful_heartbeat_at": readiness.last_successful_heartbeat_at,
                "stale_workers": stale_workers,
                "prometheus_failed_jobs": _gauge_value(
                    prometheus_metrics.worker_failed_job_count
                ),
            },
        )

    async def _storage(self) -> DiagnosticsSection:
        if not object_storage.is_configured and not settings.RAG_ENABLED:
            return DiagnosticsSection(
                state="not_required",
                detail="Object storage not configured and not required",
                metrics={"configured": False, "bucket_configured": False},
            )
        ok, detail = await object_storage.readiness()
        state: OperationalState = "healthy" if ok else "unavailable"
        if not object_storage.is_configured and settings.RAG_ENABLED:
            state = "unavailable"
        return DiagnosticsSection(
            state=state,
            detail=detail,
            metrics={
                "configured": object_storage.is_configured,
                "bucket_configured": bool(settings.STORAGE_BUCKET),
                "bucket_name": settings.STORAGE_BUCKET or None,
                "endpoint_host": _safe_host(settings.STORAGE_ENDPOINT_URL or None),
                "region": settings.STORAGE_REGION,
            },
        )

    async def _ai_providers(self) -> list[AiProviderDiagnostics]:
        # Configuration-only probe — never call paid provider APIs from diagnostics.
        configured_map = {
            "local": True,
            "openai": bool(settings.OPENAI_API_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
        }
        embedding_avg = _histogram_avg(rag_metrics.rag_embedding_latency_ms)
        providers: list[AiProviderDiagnostics] = []
        for descriptor in AiProviderService.list_provider_descriptors():
            key = descriptor.key
            configured = configured_map.get(key, False)
            if key == "local":
                state: OperationalState = "healthy"
                detail = "Local heuristic provider always available"
            elif configured:
                state = "healthy"
                detail = "API key configured (live probe skipped)"
            else:
                state = "not_required"
                detail = "API key not configured"
            providers.append(
                AiProviderDiagnostics(
                    key=key,
                    label=descriptor.label,
                    configured=configured,
                    state=state,
                    detail=detail,
                    supports_generation=descriptor.supports_generation,
                    supports_embeddings=descriptor.supports_embeddings,
                    latency_summary_ms=(
                        embedding_avg if key == settings.AI_EMBEDDING_PROVIDER else None
                    ),
                )
            )
        return providers

    async def _rag(self) -> DiagnosticsSection:
        if not settings.RAG_ENABLED:
            return DiagnosticsSection(
                state="not_required",
                detail="RAG is disabled",
                metrics={"enabled": False},
            )
        try:
            summary = await IndexVersionService(self.db).status_summary()
            active = summary["active_version"]
            vector = await pgvector_readiness(self.db)
            state: OperationalState = "healthy" if vector.available else "unavailable"
            if vector.available and int(summary["jobs_failed"] or 0) > 0:
                state = "degraded"
            return DiagnosticsSection(
                state=state,
                detail="RAG index ready" if state == "healthy" else (
                    "pgvector unavailable" if not vector.available else "RAG has failed ingestions"
                ),
                metrics={
                    "enabled": True,
                    "vector_ready": vector.available,
                    "active_index_version": getattr(active, "key", None),
                    "embedding_provider": getattr(active, "embedding_provider", None),
                    "embedding_model": getattr(active, "embedding_model", None),
                    "documents_total": summary["documents_total"],
                    "documents_indexed": summary["documents_indexed"],
                    "documents_stale": summary["documents_stale"],
                    "documents_current": summary["documents_current"],
                    "ingestion_jobs_active": summary["jobs_active"],
                    "ingestion_jobs_failed": summary["jobs_failed"],
                    "retrieval_latency_ms_avg": _histogram_avg(
                        rag_metrics.rag_retrieval_latency_ms
                    ),
                    "embedding_latency_ms_avg": _histogram_avg(
                        rag_metrics.rag_embedding_latency_ms
                    ),
                    "cache_hit_ratio": _cache_hit_ratio(),
                    "vector_unavailable_total": _counter_sum(
                        rag_metrics.rag_vector_unavailable_total
                    ),
                    "retrieval_degraded_total": _counter_sum(
                        rag_metrics.rag_retrieval_degraded_total
                    ),
                },
            )
        except Exception as exc:
            return DiagnosticsSection(
                state="unavailable",
                detail=f"RAG diagnostics failed ({type(exc).__name__})",
                metrics={"enabled": True},
            )


__all__ = ["DiagnosticsService", "_assert_no_secrets", "_safe_host"]
