from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobsConsoleListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class JobConsoleItemResponse(BaseModel):
    id: str
    source: str
    task_id: str
    job_type: str
    queue: str
    state: str
    raw_status: str
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    available_at: str | None = None
    duration_seconds: float | None = None
    attempts: int = 0
    max_attempts: int = 0
    retries: int = 0
    related_user_id: str | None = None
    related_project_id: str | None = None
    related_document_id: str | None = None
    correlation_id: str | None = None
    operation_id: str | None = None
    error_classification: str | None = None
    safe_error_summary: str | None = None
    stale: bool = False
    can_retry: bool = False
    can_cancel: bool = False
    retry_blocked_reason: str | None = None
    cancel_blocked_reason: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    trace_hints: dict[str, Any] | None = None
