from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic

import httpx
from fastapi import HTTPException

from backend.core.config import settings
from backend.modules.ai import metrics
from backend.observability.instruments import set_current_span_attributes

_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
_MAX_HTTP_RETRIES = 3
_provider_semaphore: asyncio.Semaphore | None = None
_provider_semaphore_loop = None
_provider_semaphore_limit: int | None = None


def _get_provider_semaphore() -> asyncio.Semaphore:
    global _provider_semaphore, _provider_semaphore_limit, _provider_semaphore_loop
    loop = asyncio.get_running_loop()
    limit = max(1, settings.AI_MAX_CONCURRENT_PROVIDER_CALLS)
    if (
        _provider_semaphore is None
        or _provider_semaphore_loop is not loop
        or _provider_semaphore_limit != limit
    ):
        _provider_semaphore = asyncio.Semaphore(limit)
        _provider_semaphore_loop = loop
        _provider_semaphore_limit = limit
    return _provider_semaphore


@dataclass(frozen=True, slots=True)
class ProviderRetryMetadata:
    attempts: int
    retries: int
    last_status_code: int | None = None
    deadline_exceeded: bool = False


class ProviderDeadlineExceeded(TimeoutError):
    def __init__(self, message: str, metadata: ProviderRetryMetadata):
        super().__init__(message)
        self.metadata = metadata


class ProviderTransportError(RuntimeError):
    def __init__(self, message: str, metadata: ProviderRetryMetadata):
        super().__init__(message)
        self.metadata = metadata


class ProviderHTTPError(HTTPException):
    def __init__(self, *, provider: str, response: httpx.Response, detail: str | None = None):
        metadata = response_retry_metadata(response)
        super().__init__(
            status_code=502,
            detail=detail or f"{provider} request failed: {response.text[:300]}",
        )
        self.metadata = metadata


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    idempotent: bool = True,
    provider_key: str = "unknown",
    operation: str = "request",
    trace_attributes: dict[str, str | int | float | bool] | None = None,
    **kwargs,
) -> httpx.Response:
    set_current_span_attributes(
        module="ai",
        provider=provider_key,
        operation=operation,
        **(trace_attributes or {}),
    )
    max_retries = min(_MAX_HTTP_RETRIES, max(0, settings.AI_PROVIDER_MAX_RETRIES))
    deadline = monotonic() + max(0.001, settings.AI_REQUEST_TIMEOUT_SECONDS)
    for attempt in range(max_retries + 1):
        remaining = deadline - monotonic()
        if remaining <= 0:
            metadata = ProviderRetryMetadata(
                attempts=attempt,
                retries=max(0, attempt - 1),
                deadline_exceeded=True,
            )
            metrics.ai_provider_timeout_total.labels(provider_key, operation).inc()
            raise ProviderDeadlineExceeded("AI provider deadline exceeded", metadata)
        attempts = attempt + 1
        metadata = ProviderRetryMetadata(attempts=attempts, retries=attempt)
        try:
            request_kwargs = {**kwargs, "timeout": provider_timeout(remaining)}
            async with _get_provider_semaphore():
                response = await client.post(url, **request_kwargs)
        except httpx.TimeoutException as exc:
            metrics.ai_provider_request_total.labels(provider_key, operation, "timeout").inc()
            if not idempotent or attempt == max_retries:
                metrics.ai_provider_timeout_total.labels(provider_key, operation).inc()
                raise ProviderDeadlineExceeded(
                    "AI provider request timed out", metadata
                ) from exc
            delay = retry_delay(attempt, retry_after=None)
            if delay >= max(0.0, deadline - monotonic()):
                metrics.ai_provider_timeout_total.labels(provider_key, operation).inc()
                raise ProviderDeadlineExceeded(
                    "AI provider deadline exceeded", metadata
                ) from exc
            metrics.ai_provider_retry_total.labels(provider_key, operation, "timeout").inc()
            await asyncio.sleep(delay)
            continue
        except httpx.TransportError as exc:
            metrics.ai_provider_request_total.labels(
                provider_key, operation, "transport_error"
            ).inc()
            if not idempotent or attempt == max_retries:
                raise ProviderTransportError(
                    "AI provider transport failed", metadata
                ) from exc
            delay = retry_delay(attempt, retry_after=None)
            if delay >= max(0.0, deadline - monotonic()):
                metrics.ai_provider_timeout_total.labels(provider_key, operation).inc()
                raise ProviderDeadlineExceeded(
                    "AI provider deadline exceeded", metadata
                ) from exc
            metrics.ai_provider_retry_total.labels(
                provider_key, operation, "transport_error"
            ).inc()
            await asyncio.sleep(delay)
            continue

        response_metadata = ProviderRetryMetadata(
            attempts=attempts,
            retries=attempt,
            last_status_code=response.status_code,
        )
        set_response_retry_metadata(response, response_metadata)
        set_current_span_attributes(
            provider_attempts=attempts,
            provider_retry_count=attempt,
            provider_last_status_code=response.status_code,
        )
        retryable = response.status_code in _RETRYABLE_STATUS_CODES
        if not idempotent or not retryable or attempt == max_retries:
            metrics.ai_provider_request_total.labels(
                provider_key,
                operation,
                "ok" if response.status_code < 400 else str(response.status_code),
            ).inc()
            return response
        delay = retry_delay(attempt, retry_after=response.headers.get("Retry-After"))
        if delay >= max(0.0, deadline - monotonic()):
            metrics.ai_provider_timeout_total.labels(provider_key, operation).inc()
            raise ProviderDeadlineExceeded(
                "AI provider deadline exceeded", response_metadata
            )
        metrics.ai_provider_request_total.labels(provider_key, operation, "retry").inc()
        metrics.ai_provider_retry_total.labels(
            provider_key, operation, "http_status"
        ).inc()
        await asyncio.sleep(delay)


def provider_timeout(remaining_seconds: float) -> httpx.Timeout:
    total = max(0.001, remaining_seconds)
    return httpx.Timeout(
        timeout=total,
        connect=min(10.0, total),
        read=total,
        write=total,
        pool=min(5.0, total),
    )


def retry_delay(attempt: int, *, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(
                max(0.0, float(retry_after)),
                settings.AI_PROVIDER_BACKOFF_MAX_SECONDS,
            )
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return min(
                    max(0.0, (retry_at - datetime.now(UTC)).total_seconds()),
                    settings.AI_PROVIDER_BACKOFF_MAX_SECONDS,
                )
            except (TypeError, ValueError, OverflowError):
                pass
    base = min(2**attempt, settings.AI_PROVIDER_BACKOFF_MAX_SECONDS)
    jitter = 0.0
    if attempt > 0:
        jitter = random.uniform(
            0.0,
            min(settings.AI_PROVIDER_BACKOFF_JITTER_SECONDS, base * 0.25),
        )
    return min(base + jitter, settings.AI_PROVIDER_BACKOFF_MAX_SECONDS)


def set_response_retry_metadata(
    response: httpx.Response, metadata: ProviderRetryMetadata
) -> None:
    response.extensions = {
        **(response.extensions if isinstance(response.extensions, dict) else {}),
        "provider_retry": metadata,
    }


def response_retry_metadata(response: httpx.Response) -> ProviderRetryMetadata:
    extensions = response.extensions if isinstance(response.extensions, dict) else {}
    metadata = extensions.get("provider_retry")
    if isinstance(metadata, ProviderRetryMetadata):
        return metadata
    return ProviderRetryMetadata(
        attempts=1,
        retries=0,
        last_status_code=getattr(response, "status_code", None),
    )


def result_retry_fields(response: httpx.Response) -> dict[str, int | None]:
    metadata = response_retry_metadata(response)
    return {
        "attempts": metadata.attempts,
        "retries": metadata.retries,
        "last_status_code": metadata.last_status_code,
    }
