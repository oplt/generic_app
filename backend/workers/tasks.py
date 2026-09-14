from backend.core.config import settings
from backend.modules.memory.workers import extract_turn_memories_sync
from backend.modules.rag.workers import cleanup_document_sync, index_document_sync
from backend.workers.ai_generation import run_ai_generation_sync
from backend.workers.async_dispatch import run_async_in_sync_context
from backend.workers.celery_app import celery_app
from backend.workers.effect_ledger import ExternalEffectInFlightError
from backend.workers.email import send_email_sync
from backend.workers.evaluation import run_evaluation_sync
from backend.workers.job_service import run_tracked_sync
from backend.workers.outbox import dispatch_pending_job_events


def _task_max_attempts(task) -> int:
    retries = getattr(task, "max_retries", None)
    if retries is None:
        return settings.WORKER_JOB_DEFAULT_MAX_ATTEMPTS
    return int(retries) + 1


@celery_app.task(
    bind=True,
    name="backend.workers.tasks.send_email_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_email_task(
    self,
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    operation_id: str | None = None,
) -> None:
    operation = operation_id or f"email:{to}:{subject}"
    try:
        run_tracked_sync(
            job_type="email",
            payload={"to": to, "subject": subject, "operation_id": operation},
            runner=lambda: send_email_sync(
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                operation_id=operation,
            ),
            correlation_id=operation,
            operation_id=operation,
            max_attempts=_task_max_attempts(self),
        )
    except ExternalEffectInFlightError as exc:
        raise self.retry(
            exc=exc,
            countdown=settings.EXTERNAL_EFFECT_LEASE_SECONDS,
        ) from exc


@celery_app.task(
    bind=True,
    name="backend.workers.tasks.index_rag_document_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def index_rag_document_task(
    self,
    *,
    document_id: str,
    user_id: str,
    job_id: str | None = None,
) -> None:
    operation = job_id or f"rag-document:{document_id}"
    try:
        run_tracked_sync(
            job_type="rag-indexing",
            payload={"document_id": document_id, "user_id": user_id, "job_id": job_id},
            runner=lambda: index_document_sync(
                document_id=document_id, user_id=user_id, job_id=job_id
            ),
            correlation_id=operation,
            operation_id=operation,
            max_attempts=_task_max_attempts(self),
        )
    except Exception as exc:
        from backend.modules.rag.application.document_ingestion_service import (
            IngestionJobBusyError,
        )

        if isinstance(exc, IngestionJobBusyError):
            raise self.retry(
                exc=exc,
                countdown=settings.OUTBOX_DISPATCH_LEASE_SECONDS,
            ) from exc
        raise


@celery_app.task(
    bind=True,
    name="backend.workers.tasks.cleanup_rag_document_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def cleanup_rag_document_task(
    self,
    *,
    document_id: str,
    user_id: str,
    storage_path: str | None,
) -> None:
    operation = f"rag-cleanup:{document_id}"
    run_tracked_sync(
        job_type="rag-cleanup",
        payload={"document_id": document_id, "user_id": user_id},
        runner=lambda: cleanup_document_sync(
            document_id=document_id, user_id=user_id, storage_path=storage_path
        ),
        correlation_id=operation,
        operation_id=operation,
        max_attempts=_task_max_attempts(self),
    )


@celery_app.task(name="backend.workers.tasks.cleanup_chat_retention_task")
def cleanup_chat_retention_task() -> int:
    result = 0

    def run() -> None:
        nonlocal result
        from backend.db.session import SessionLocal
        from backend.db.transaction import rollback_safely
        from backend.modules.chat.service import DocumentChatService
        from backend.workers.schedule_lock import release_beat_lock, try_acquire_beat_lock

        async def _cleanup() -> int:
            lock_token = await try_acquire_beat_lock(
                "chat-retention", on_redis_error="proceed"
            )
            if lock_token is None:
                return 0
            try:
                async with SessionLocal() as db:
                    try:
                        return await DocumentChatService(db).delete_expired_conversations()
                    except Exception:
                        await rollback_safely(db, owner="worker.chat_retention")
                        raise
            finally:
                await release_beat_lock("chat-retention", lock_token)

        result = run_async_in_sync_context(_cleanup())

    # Scheduled beat jobs intentionally omit operation_id so each tick is a new logical job.
    run_tracked_sync(
        job_type="chat-retention",
        payload={},
        runner=run,
        correlation_id="chat-retention",
        max_attempts=1,
        retryable=False,
    )
    return result


@celery_app.task(name="backend.workers.tasks.cleanup_idempotency_records_task")
def cleanup_idempotency_records_task() -> int:
    result = 0

    def run() -> None:
        nonlocal result
        from backend.db.session import SessionLocal
        from backend.lib.idempotency import cleanup_expired_idempotency_records
        from backend.workers.schedule_lock import release_beat_lock, try_acquire_beat_lock

        async def _cleanup() -> int:
            lock_token = await try_acquire_beat_lock(
                "idempotency-cleanup", on_redis_error="proceed"
            )
            if lock_token is None:
                return 0
            try:
                async with SessionLocal() as db:
                    return await cleanup_expired_idempotency_records(db)
            finally:
                await release_beat_lock("idempotency-cleanup", lock_token)

        result = run_async_in_sync_context(_cleanup())

    run_tracked_sync(
        job_type="idempotency-cleanup",
        payload={},
        runner=run,
        correlation_id="idempotency-cleanup",
        max_attempts=1,
        retryable=False,
    )
    return result


@celery_app.task(name="backend.workers.tasks.cleanup_retired_rag_index_versions_task")
def cleanup_retired_rag_index_versions_task() -> dict[str, int]:
    result: dict[str, int] = {"versions_considered": 0, "chunks_deleted": 0}

    def run() -> None:
        nonlocal result
        from backend.db.session import SessionLocal
        from backend.modules.rag.application.index_version_service import IndexVersionService
        from backend.workers.schedule_lock import release_beat_lock, try_acquire_beat_lock

        async def _cleanup() -> dict[str, int]:
            lock_token = await try_acquire_beat_lock(
                "rag-index-retention", on_redis_error="proceed"
            )
            if lock_token is None:
                return {"versions_considered": 0, "chunks_deleted": 0}
            try:
                async with SessionLocal() as db:
                    return await IndexVersionService(db).cleanup_retired_versions()
            finally:
                await release_beat_lock("rag-index-retention", lock_token)

        result = run_async_in_sync_context(_cleanup())

    run_tracked_sync(
        job_type="rag-index-retention",
        payload={},
        runner=run,
        correlation_id="rag-index-retention",
        max_attempts=1,
        retryable=False,
    )
    return result


@celery_app.task(name="backend.workers.tasks.run_ai_evaluation_task")
def run_ai_evaluation_task(
    *,
    evaluation_run_id: str,
    user_id: str,
    dataset_id: str,
    prompt_version_id: str,
) -> None:
    run_tracked_sync(
        job_type="ai-evaluation",
        payload={"evaluation_run_id": evaluation_run_id, "user_id": user_id},
        runner=lambda: run_evaluation_sync(
            evaluation_run_id=evaluation_run_id,
            user_id=user_id,
            dataset_id=dataset_id,
            prompt_version_id=prompt_version_id,
        ),
        correlation_id=evaluation_run_id,
        operation_id=evaluation_run_id,
        max_attempts=1,
        retryable=False,
    )


@celery_app.task(name="backend.workers.tasks.run_ai_generation_task")
def run_ai_generation_task(
    *,
    user_id: str,
    prompt_template_key: str | None,
    prompt_version_id: str | None,
    variables: dict,
    retrieval_query: str | None,
    document_ids: list[str],
    top_k: int,
    review_required: bool,
) -> None:
    operation = f"ai-generation:{user_id}:{prompt_version_id or prompt_template_key}"
    run_tracked_sync(
        job_type="ai-generation",
        payload={"user_id": user_id, "prompt_version_id": prompt_version_id},
        runner=lambda: run_ai_generation_sync(
            user_id=user_id,
            prompt_template_key=prompt_template_key,
            prompt_version_id=prompt_version_id,
            variables=variables,
            retrieval_query=retrieval_query,
            document_ids=document_ids,
            top_k=top_k,
            review_required=review_required,
        ),
        correlation_id=operation,
        operation_id=operation,
        max_attempts=1,
        retryable=False,
    )


@celery_app.task(
    bind=True,
    name="backend.workers.tasks.extract_turn_memories_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def extract_turn_memories_task(
    self,
    *,
    user_id: str,
    agent_id: str,
    run_id: str,
    project_id: str | None,
    user_message: str,
    assistant_message: str,
    source_message_id: str,
) -> None:
    run_tracked_sync(
        job_type="memory-extraction",
        payload={"user_id": user_id, "source_message_id": source_message_id},
        runner=lambda: extract_turn_memories_sync(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            project_id=project_id,
            user_message=user_message,
            assistant_message=assistant_message,
            source_message_id=source_message_id,
        ),
        correlation_id=source_message_id,
        operation_id=source_message_id,
        max_attempts=_task_max_attempts(self),
    )


@celery_app.task(name="backend.workers.tasks.dispatch_outbox_task")
def dispatch_outbox_task() -> int:
    result = 0

    def run() -> None:
        nonlocal result

        from backend.db.session import SessionLocal
        from backend.workers.schedule_lock import release_beat_lock, try_acquire_beat_lock

        async def _dispatch() -> int:
            # Fail-open on Redis: SKIP LOCKED + lease tokens remain the safety net.
            lock_token = await try_acquire_beat_lock(
                "outbox-dispatch", on_redis_error="proceed"
            )
            if lock_token is None:
                return 0
            try:
                async with SessionLocal() as db:
                    return await dispatch_pending_job_events(db)
            finally:
                await release_beat_lock("outbox-dispatch", lock_token)

        result = run_async_in_sync_context(_dispatch())

    # Beat-driven; each tick is a distinct logical job.
    run_tracked_sync(
        job_type="outbox-dispatch",
        payload={},
        runner=run,
        max_attempts=1,
        retryable=False,
    )
    return result


@celery_app.task(name="backend.workers.tasks.enqueue_outbox_job")
def enqueue_outbox_job(*, job_type: str, document_id: str, user_id: str, job_id: str) -> None:
    if job_type != "rag-indexing":
        raise ValueError(f"Unsupported outbox job type: {job_type}")
    from backend.workers.job_service import ensure_queued_job

    run_async_in_sync_context(
        ensure_queued_job(
            job_type="rag-indexing",
            payload={"document_id": document_id, "user_id": user_id, "job_id": job_id},
            correlation_id=job_id,
            operation_id=job_id,
            max_attempts=4,
        )
    )
    index_rag_document_task.apply_async(
        kwargs={"document_id": document_id, "user_id": user_id, "job_id": job_id}
    )
