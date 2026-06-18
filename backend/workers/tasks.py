from backend.workers.celery_app import celery_app
from backend.workers.email import send_email_sync
from backend.workers.rag_indexing import index_document_sync


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
    send_email_sync(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )


@celery_app.task(
    name="backend.workers.tasks.index_rag_document_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def index_rag_document_task(*, document_id: str, user_id: str) -> None:
    index_document_sync(document_id=document_id, user_id=user_id)
