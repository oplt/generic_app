"""Request-scoped developer diagnostics collector (OTEL-adjacent, flag-gated).

Lives under observability so instrumentation hooks stay within that package
boundary. The HTTP/UI surface remains in ``backend.modules.developer_diagnostics``.
"""

from __future__ import annotations

import threading
from collections import deque
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any

from backend.core.config import settings

DIAGNOSTICS_HEADER = "X-Developer-Diagnostics"
TRACE_ID_HEADER = "X-Trace-Id"
_MAX_RECENT = 50
_MAX_LIST_ITEMS = 20

_current: ContextVar[RequestDiagnostics | None] = ContextVar(
    "developer_request_diagnostics", default=None
)
_recent: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT)
_recent_lock = threading.Lock()
_listeners_installed = False


@dataclass
class RequestDiagnostics:
    method: str = ""
    path: str = ""
    status_code: int | None = None
    duration_ms: float = 0.0
    correlation_id: str | None = None
    trace_id: str | None = None
    sql_query_count: int = 0
    db_duration_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    external_calls: list[dict[str, Any]] = field(default_factory=list)
    celery_tasks: list[str] = field(default_factory=list)
    rag_stages: list[str] = field(default_factory=list)
    rag_retrieved_chunk_count: int | None = None
    _db_timer_start: float | None = field(default=None, repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        """Safe summary — never includes bodies, SQL text, or credentials."""

        return {
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "duration_ms": round(self.duration_ms, 2),
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "sql_query_count": self.sql_query_count,
            "db_duration_ms": round(self.db_duration_ms, 2),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "external_calls": self.external_calls[:_MAX_LIST_ITEMS],
            "celery_tasks": self.celery_tasks[:_MAX_LIST_ITEMS],
            "rag_stages": self.rag_stages[:_MAX_LIST_ITEMS],
            "rag_retrieved_chunk_count": self.rag_retrieved_chunk_count,
        }


def is_enabled() -> bool:
    return bool(settings.DEVELOPER_DIAGNOSTICS_ENABLED)


def current() -> RequestDiagnostics | None:
    return _current.get()


def begin_request(*, method: str, path: str, correlation_id: str | None) -> Token | None:
    if not is_enabled():
        return None
    snapshot = RequestDiagnostics(
        method=method,
        path=path,
        correlation_id=correlation_id,
        trace_id=_current_trace_id(),
    )
    return _current.set(snapshot)


def finish_request(
    token: Token | None,
    *,
    status_code: int,
    duration_ms: float,
) -> dict[str, Any] | None:
    if token is None:
        return None
    snapshot = _current.get()
    try:
        if snapshot is None:
            return None
        snapshot.status_code = status_code
        snapshot.duration_ms = duration_ms
        if not snapshot.trace_id:
            snapshot.trace_id = _current_trace_id()
        payload = snapshot.to_public_dict()
        with _recent_lock:
            _recent.appendleft(payload)
        return payload
    finally:
        _current.reset(token)


def recent_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    with _recent_lock:
        return list(_recent)[: max(1, min(limit, _MAX_RECENT))]


def clear_recent() -> None:
    with _recent_lock:
        _recent.clear()


def record_sql_start() -> None:
    snapshot = _current.get()
    if snapshot is None:
        return
    snapshot._db_timer_start = perf_counter()


def record_sql_end() -> None:
    snapshot = _current.get()
    if snapshot is None:
        return
    snapshot.sql_query_count += 1
    started = snapshot._db_timer_start
    snapshot._db_timer_start = None
    if started is not None:
        snapshot.db_duration_ms += (perf_counter() - started) * 1000.0


def record_cache_hit() -> None:
    snapshot = _current.get()
    if snapshot is not None:
        snapshot.cache_hits += 1


def record_cache_miss() -> None:
    snapshot = _current.get()
    if snapshot is not None:
        snapshot.cache_misses += 1


def record_external_call(
    *,
    provider: str,
    operation: str,
    latency_ms: float | None = None,
) -> None:
    snapshot = _current.get()
    if snapshot is None:
        return
    if len(snapshot.external_calls) >= _MAX_LIST_ITEMS:
        return
    entry: dict[str, Any] = {
        "provider": str(provider)[:64],
        "operation": str(operation)[:64],
    }
    if latency_ms is not None:
        entry["latency_ms"] = round(float(latency_ms), 2)
    snapshot.external_calls.append(entry)


def record_celery_task(job_name: str) -> None:
    snapshot = _current.get()
    if snapshot is None:
        return
    if len(snapshot.celery_tasks) >= _MAX_LIST_ITEMS:
        return
    name = str(job_name)[:128]
    if name not in snapshot.celery_tasks:
        snapshot.celery_tasks.append(name)


def record_rag_stage(stage: str) -> None:
    snapshot = _current.get()
    if snapshot is None:
        return
    if len(snapshot.rag_stages) >= _MAX_LIST_ITEMS:
        return
    label = str(stage)[:64]
    if label not in snapshot.rag_stages:
        snapshot.rag_stages.append(label)


def record_rag_chunks(count: int) -> None:
    snapshot = _current.get()
    if snapshot is not None:
        snapshot.rag_retrieved_chunk_count = int(count)


def _current_trace_id() -> str | None:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is not None and getattr(ctx, "is_valid", False):
            return format(ctx.trace_id, "032x")
    except Exception:
        return None
    return None


def ensure_sqlalchemy_listeners() -> None:
    """Install once; listeners no-op when no active request collector."""

    global _listeners_installed
    if _listeners_installed:
        return
    from sqlalchemy import event

    from backend.db.session import engine

    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        del conn, cursor, statement, parameters, context, executemany
        record_sql_start()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        del conn, cursor, statement, parameters, context, executemany
        record_sql_end()

    _listeners_installed = True


def asdict_safe(snapshot: RequestDiagnostics) -> dict[str, Any]:
    data = asdict(snapshot)
    data.pop("_db_timer_start", None)
    return data
