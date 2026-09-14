"""Operational jobs console — aggregate application_jobs + RAG ingestion jobs."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService
from backend.modules.rag.domain.enums import IngestionJobStatus
from backend.modules.rag.infrastructure.models import RagIngestionJob
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.workers.job_service import (
    STATUS_DEAD_LETTER,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    _is_stale_running,
)
from backend.workers.models import ApplicationJob, BackgroundJobOutbox

STATUS_CANCELLED = "cancelled"
STATUS_RETRYING = "retrying"
STATUS_STALE = "stale"

QUEUE_BY_JOB_TYPE: dict[str, str] = {
    "email": "email",
    "rag-indexing": "ingestion",
    "rag-cleanup": "cleanup",
    "chat-retention": "cleanup",
    "idempotency-cleanup": "cleanup",
    "ai-evaluation": "evaluation",
    "ai-generation": "ai",
    "memory-extraction": "memory",
    "outbox-dispatch": "default",
}

_SECRET_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|credential|cookie)",
    re.I,
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _safe_error(message: str | None) -> tuple[str | None, str | None]:
    if not message:
        return None, None
    cleaned = message.strip().replace("\n", " ")
    if len(cleaned) > 240:
        cleaned = f"{cleaned[:237]}..."
    classification = cleaned.split(":", 1)[0].strip() or "Error"
    return classification, cleaned


def _redact_payload_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Never return secret-bearing values — only safe structural hints."""

    raw = payload or {}
    field_names = raw.get("field_names")
    if isinstance(field_names, list):
        names = [str(name) for name in field_names]
    else:
        names = sorted(str(key) for key in raw.keys())
    safe_names = [name for name in names if not _SECRET_KEY_RE.search(name)]
    return {
        "field_names": safe_names,
        "field_count": len(names),
        "redacted_field_count": len(names) - len(safe_names),
        "source": raw.get("source") if isinstance(raw.get("source"), str) else None,
    }


def _duration_seconds(
    started: datetime | None, finished: datetime | None, *, now: datetime
) -> float | None:
    start = _aware(started)
    if start is None:
        return None
    end = _aware(finished) or now
    return round(max(0.0, (end - start).total_seconds()), 3)


def _console_state_for_application(job: ApplicationJob, *, now: datetime) -> str:
    if job.status == STATUS_RUNNING and _is_stale_running(job, now=now):
        return STATUS_STALE
    if job.status == STATUS_QUEUED:
        available = _aware(job.available_at)
        if available and available > now and (job.attempts or 0) > 0:
            return STATUS_RETRYING
        return STATUS_QUEUED
    if job.status == STATUS_SUCCEEDED:
        return "succeeded"
    if job.status == STATUS_FAILED:
        return "failed"
    if job.status == STATUS_DEAD_LETTER:
        return "failed"
    if job.status == STATUS_CANCELLED:
        return "cancelled"
    return job.status


def _console_state_for_rag(job: RagIngestionJob, *, now: datetime) -> str:
    if job.status in {IngestionJobStatus.PENDING.value, "queued"}:
        return STATUS_QUEUED
    if job.status == IngestionJobStatus.RUNNING.value:
        heartbeat = _aware(job.heartbeat_at) or _aware(job.started_at)
        lease = timedelta(seconds=settings.OUTBOX_DISPATCH_LEASE_SECONDS)
        if heartbeat is None or heartbeat <= now - lease:
            return STATUS_STALE
        return STATUS_RUNNING
    if job.status == IngestionJobStatus.COMPLETED.value:
        return "succeeded"
    if job.status == IngestionJobStatus.FAILED.value:
        return "failed"
    if job.status == STATUS_CANCELLED:
        return "cancelled"
    return job.status


class JobsConsoleService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.rag_repo = RagRepository(db)

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        queue: str | None = None,
        project_id: str | None = None,
        failed_only: bool = False,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        now = datetime.now(UTC)
        application_rows = await self._list_application_jobs(
            job_type=job_type,
            project_id=project_id,
            created_after=created_after,
            created_before=created_before,
            limit=500,
        )
        rag_rows = await self._list_rag_jobs(
            project_id=project_id,
            created_after=created_after,
            created_before=created_before,
            limit=500,
        )
        items = [
            *[self._serialize_application(row, now=now) for row in application_rows],
            *[self._serialize_rag(row, now=now) for row in rag_rows],
        ]
        items = self._apply_filters(
            items,
            status=status,
            job_type=job_type,
            queue=queue,
            failed_only=failed_only,
        )
        items.sort(key=lambda item: item["created_at"] or "", reverse=True)
        total = len(items)
        return items[offset : offset + limit], total

    async def get_job(self, job_id: str, *, source: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        if source in {None, "application"}:
            app_job = await self.db.get(ApplicationJob, job_id)
            if app_job is not None:
                return self._serialize_application(app_job, now=now, detail=True)
        if source in {None, "rag_ingestion"}:
            rag_job = await self.rag_repo.get_ingestion_job(job_id)
            if rag_job is not None:
                return self._serialize_rag(rag_job, now=now, detail=True)
        raise HTTPException(status_code=404, detail="Job not found")

    async def retry_job(
        self,
        job_id: str,
        *,
        actor_id: str,
        is_admin: bool,
        source: str | None = None,
    ) -> dict[str, Any]:
        detail = await self.get_job(job_id, source=source)
        if not detail["can_retry"]:
            raise HTTPException(
                status_code=409,
                detail=detail.get("retry_blocked_reason") or "Job cannot be retried",
            )
        if detail["source"] == "rag_ingestion":
            service = DocumentIngestionService(self.db)
            job = await service.enqueue_document_indexing(
                document_id=detail["related_document_id"],
                user_id=detail["related_user_id"] or actor_id,
                is_admin=is_admin,
                force_new_attempt=True,
            )
            await self.db.commit()
            return await self.get_job(job.id, source="rag_ingestion")

        # application rag-indexing linked by operation_id == rag job id
        if detail["job_type"] == "rag-indexing" and detail.get("operation_id"):
            rag = await self.rag_repo.get_ingestion_job(detail["operation_id"])
            if rag is None:
                raise HTTPException(status_code=409, detail="Linked RAG job not found")
            service = DocumentIngestionService(self.db)
            job = await service.enqueue_document_indexing(
                document_id=rag.document_id,
                user_id=rag.user_id,
                is_admin=is_admin,
                force_new_attempt=True,
            )
            await self.db.commit()
            return await self.get_job(job.id, source="rag_ingestion")

        raise HTTPException(
            status_code=409,
            detail="Retry from console is only supported for RAG ingestion jobs",
        )

    async def cancel_job(
        self, job_id: str, *, source: str | None = None
    ) -> dict[str, Any]:
        detail = await self.get_job(job_id, source=source)
        if not detail["can_cancel"]:
            raise HTTPException(
                status_code=409,
                detail=detail.get("cancel_blocked_reason") or "Job cannot be cancelled",
            )
        now = datetime.now(UTC)
        if detail["source"] == "application":
            job = await self.db.get(ApplicationJob, job_id)
            if job is None or job.status != STATUS_QUEUED:
                raise HTTPException(status_code=409, detail="Only queued application jobs can be cancelled")
            job.status = STATUS_CANCELLED
            job.finished_at = now
            job.last_error = "cancelled_by_operator"
            await self.db.commit()
            return await self.get_job(job_id, source="application")

        rag = await self.rag_repo.get_ingestion_job(job_id)
        if rag is None or rag.status not in {IngestionJobStatus.PENDING.value, "queued"}:
            raise HTTPException(status_code=409, detail="Only pending RAG jobs can be cancelled")
        await self.rag_repo.update_ingestion_job(
            rag,
            status=IngestionJobStatus.CANCELLED,
            error_message="cancelled_by_operator",
            finished=True,
        )
        await self.db.execute(
            update(BackgroundJobOutbox)
            .where(
                BackgroundJobOutbox.job_id == job_id,
                BackgroundJobOutbox.status.in_(("pending", "dispatching")),
            )
            .values(status=STATUS_CANCELLED, last_error="cancelled_by_operator")
        )
        await self.db.commit()
        return await self.get_job(job_id, source="rag_ingestion")

    async def _list_application_jobs(
        self,
        *,
        job_type: str | None,
        project_id: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        limit: int,
    ) -> list[ApplicationJob]:
        clauses = []
        if job_type:
            clauses.append(ApplicationJob.job_type == job_type)
        if created_after:
            clauses.append(ApplicationJob.created_at >= created_after)
        if created_before:
            clauses.append(ApplicationJob.created_at <= created_before)
        # project_id lives only in redacted payload field_names — skip hard filter here;
        # post-filter in serializer path when project_id requested uses related fields.
        stmt: Select = (
            select(ApplicationJob)
            .where(*clauses)
            .order_by(ApplicationJob.created_at.desc())
            .limit(limit)
        )
        rows = list((await self.db.scalars(stmt)).all())
        if project_id:
            # Application payloads are redacted; cannot filter by project reliably.
            return []
        return rows

    async def _list_rag_jobs(
        self,
        *,
        project_id: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        limit: int,
    ) -> list[RagIngestionJob]:
        clauses = []
        if project_id:
            clauses.append(RagIngestionJob.project_id == project_id)
        if created_after:
            clauses.append(RagIngestionJob.created_at >= created_after)
        if created_before:
            clauses.append(RagIngestionJob.created_at <= created_before)
        stmt = (
            select(RagIngestionJob)
            .where(*clauses)
            .order_by(RagIngestionJob.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(stmt)).all())

    def _apply_filters(
        self,
        items: list[dict[str, Any]],
        *,
        status: str | None,
        job_type: str | None,
        queue: str | None,
        failed_only: bool,
    ) -> list[dict[str, Any]]:
        filtered = items
        if status:
            if status == "failed":
                filtered = [
                    item
                    for item in filtered
                    if item["state"] in {"failed", "dead_letter"} or item.get("raw_status") == STATUS_DEAD_LETTER
                ]
            else:
                filtered = [item for item in filtered if item["state"] == status]
        if job_type:
            filtered = [item for item in filtered if item["job_type"] == job_type]
        if queue:
            filtered = [item for item in filtered if item["queue"] == queue]
        if failed_only:
            filtered = [
                item
                for item in filtered
                if item["state"] in {"failed", "stale"} or item.get("raw_status") == STATUS_DEAD_LETTER
            ]
        return filtered

    def _serialize_application(
        self, job: ApplicationJob, *, now: datetime, detail: bool = False
    ) -> dict[str, Any]:
        state = _console_state_for_application(job, now=now)
        error_class, error_summary = _safe_error(job.last_error)
        can_retry = False
        retry_blocked = "Retry from console is only supported for RAG ingestion jobs"
        if job.job_type == "rag-indexing" and job.operation_id and job.status in {
            STATUS_FAILED,
            STATUS_DEAD_LETTER,
        }:
            can_retry = True
            retry_blocked = None
        can_cancel = job.status == STATUS_QUEUED
        cancel_blocked = None if can_cancel else "Only queued application jobs can be cancelled"
        payload_summary = _redact_payload_summary(job.payload if isinstance(job.payload, dict) else {})
        item = {
            "id": job.id,
            "source": "application",
            "task_id": job.id,
            "job_type": job.job_type,
            "queue": QUEUE_BY_JOB_TYPE.get(job.job_type, "default"),
            "state": state,
            "raw_status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.finished_at.isoformat() if job.finished_at else None,
            "available_at": job.available_at.isoformat() if job.available_at else None,
            "duration_seconds": _duration_seconds(job.started_at, job.finished_at, now=now),
            "attempts": int(job.attempts or 0),
            "max_attempts": int(job.max_attempts or 0),
            "retries": max(0, int(job.attempts or 0) - 1),
            "related_user_id": None,
            "related_project_id": None,
            "related_document_id": None,
            "correlation_id": job.correlation_id,
            "operation_id": job.operation_id,
            "error_classification": error_class,
            "safe_error_summary": error_summary,
            "stale": state == STATUS_STALE,
            "can_retry": can_retry,
            "can_cancel": can_cancel,
            "retry_blocked_reason": retry_blocked,
            "cancel_blocked_reason": cancel_blocked,
            "payload_summary": payload_summary,
        }
        if detail:
            item["trace_hints"] = {
                "correlation_id": job.correlation_id,
                "operation_id": job.operation_id,
            }
        return item

    def _serialize_rag(
        self, job: RagIngestionJob, *, now: datetime, detail: bool = False
    ) -> dict[str, Any]:
        state = _console_state_for_rag(job, now=now)
        error_class, error_summary = _safe_error(job.error_message)
        can_retry = job.status in {
            IngestionJobStatus.FAILED.value,
            STATUS_CANCELLED,
            STATUS_STALE,
        } or state == STATUS_STALE
        # Allow retry for failed/stale; not for completed.
        if job.status == IngestionJobStatus.COMPLETED.value:
            can_retry = False
        can_cancel = job.status in {IngestionJobStatus.PENDING.value, "queued"}
        item = {
            "id": job.id,
            "source": "rag_ingestion",
            "task_id": job.id,
            "job_type": "rag-indexing",
            "queue": "ingestion",
            "state": state,
            "raw_status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.finished_at.isoformat() if job.finished_at else None,
            "available_at": None,
            "duration_seconds": _duration_seconds(job.started_at, job.finished_at, now=now),
            "attempts": int(job.attempts or 0),
            "max_attempts": int(settings.RAG_INGESTION_MAX_ATTEMPTS),
            "retries": max(0, int(job.attempts or 0) - 1),
            "related_user_id": job.user_id,
            "related_project_id": job.project_id,
            "related_document_id": job.document_id,
            "correlation_id": job.id,
            "operation_id": job.id,
            "error_classification": error_class,
            "safe_error_summary": error_summary,
            "stale": state == STATUS_STALE,
            "can_retry": can_retry,
            "can_cancel": can_cancel,
            "retry_blocked_reason": None
            if can_retry
            else "Only failed or stale RAG jobs can be retried",
            "cancel_blocked_reason": None
            if can_cancel
            else "Only pending RAG jobs can be cancelled",
            "payload_summary": {
                "field_names": ["document_id", "user_id", "job_id"],
                "field_count": 3,
                "redacted_field_count": 0,
                "source": "rag_ingestion",
            },
        }
        if detail:
            item["trace_hints"] = {
                "correlation_id": job.id,
                "document_id": job.document_id,
                "project_id": job.project_id,
            }
        return item
