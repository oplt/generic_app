"""Middleware that attaches per-request developer diagnostics summaries."""

from __future__ import annotations

import json
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.observability.request_diagnostics import (
    DIAGNOSTICS_HEADER,
    TRACE_ID_HEADER,
    begin_request,
    ensure_sqlalchemy_listeners,
    finish_request,
    is_enabled,
)


class DeveloperDiagnosticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not is_enabled():
            return await call_next(request)

        ensure_sqlalchemy_listeners()
        correlation_id = getattr(request.state, "correlation_id", None)
        token = begin_request(
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
        )
        started = perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (perf_counter() - started) * 1000.0
            summary = finish_request(
                token, status_code=status_code, duration_ms=duration_ms
            )
            if response is not None and summary is not None:
                response.headers[DIAGNOSTICS_HEADER] = json.dumps(
                    summary, separators=(",", ":"), ensure_ascii=True
                )
                if summary.get("trace_id"):
                    response.headers[TRACE_ID_HEADER] = str(summary["trace_id"])
