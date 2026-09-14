from backend.modules.memory.workers import extract_turn_memories_sync
from backend.modules.rag.workers import cleanup_document_sync, index_document_sync
from backend.workers.ai_generation import run_ai_generation_sync
from backend.workers.async_dispatch import run_async_in_sync_context
from backend.workers.celery_app import celery_app
from backend.workers.email import send_email_sync
from backend.workers.evaluation import run_evaluation_sync
from backend.workers.job_service import run_tracked_sync
from backend.workers.outbox import dispatch_pending_job_events


@celery_app.task(
    name="backend.workers.tasks.send_email_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_email_task(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> None:
    run_tracked_sync(
        job_type="email",
        payload={"to": to, "subject": subject},
        runner=lambda: send_email_sync(
            to=to, subject=subject, html_body=html_body, text_body=text_body
        ),
        correlation_id=f"email:{to}:{subject}",
    )


@celery_app.task(
    name="backend.workers.tasks.index_rag_document_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def index_rag_document_task(*, document_id: str, user_id: str, job_id: str | None = None) -> None:
    run_tracked_sync(
        job_type="rag-indexing",
        payload={"document_id": document_id, "user_id": user_id, "job_id": job_id},
        runner=lambda: index_document_sync(
            document_id=document_id, user_id=user_id, job_id=job_id
        ),
        correlation_id=job_id or f"rag-document:{document_id}",
    )


@celery_app.task(
    name="backend.workers.tasks.cleanup_rag_document_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def cleanup_rag_document_task(
    *,
    document_id: str,
    user_id: str,
    storage_path: str | None,
) -> None:
    run_tracked_sync(
        job_type="rag-cleanup",
        payload={"document_id": document_id, "user_id": user_id},
        runner=lambda: cleanup_document_sync(
            document_id=document_id, user_id=user_id, storage_path=storage_path
        ),
        correlation_id=f"rag-cleanup:{document_id}",
    )


@celery_app.task(name="backend.workers.tasks.cleanup_chat_retention_task")
def cleanup_chat_retention_task() -> int:
    result = 0

    def run() -> None:
        nonlocal result
        from backend.db.session import SessionLocal
        from backend.modules.chat.service import DocumentChatService

        async def _cleanup() -> int:
            async with SessionLocal() as db:
                return await DocumentChatService(db).delete_expired_conversations()

        result = run_async_in_sync_context(_cleanup())

    run_tracked_sync(
        job_type="chat-retention",
        payload={},
        runner=run,
        correlation_id="chat-retention",
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
        correlation_id=f"ai-generation:{user_id}:{prompt_version_id or prompt_template_key}",
    )


@celery_app.task(
    name="backend.workers.tasks.extract_turn_memories_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def extract_turn_memories_task(
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
    )


@celery_app.task(name="backend.workers.tasks.dispatch_outbox_task")
def dispatch_outbox_task() -> int:
    result = 0

    def run() -> None:
        nonlocal result

        from backend.db.session import SessionLocal

        async def _dispatch() -> int:
            async with SessionLocal() as db:
                return await dispatch_pending_job_events(db)

        result = run_async_in_sync_context(_dispatch())

    run_tracked_sync(job_type="outbox-dispatch", payload={}, runner=run)
    return result


@celery_app.task(name="backend.workers.tasks.enqueue_outbox_job")
def enqueue_outbox_job(*, job_type: str, document_id: str, user_id: str, job_id: str) -> None:
    if job_type != "rag-indexing":
        raise ValueError(f"Unsupported outbox job type: {job_type}")
    index_rag_document_task.apply_async(
        kwargs={"document_id": document_id, "user_id": user_id, "job_id": job_id}
    )
