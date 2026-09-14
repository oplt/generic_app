from celery import Celery

from backend.core.config import settings
from backend.core.logging import setup_logging

setup_logging()

celery_app = Celery(
    "app_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.workers.tasks"],
)

celery_app.conf.update(
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_routes={
        "backend.workers.tasks.send_email_task": {"queue": settings.CELERY_EMAIL_QUEUE},
        "backend.workers.tasks.index_rag_document_task": {
            "queue": settings.CELERY_INGESTION_QUEUE
        },
        "backend.workers.tasks.cleanup_rag_document_task": {
            "queue": settings.CELERY_CLEANUP_QUEUE
        },
        "backend.workers.tasks.cleanup_chat_retention_task": {
            "queue": settings.CELERY_CLEANUP_QUEUE
        },
        "backend.workers.tasks.run_ai_evaluation_task": {
            "queue": settings.CELERY_EVALUATION_QUEUE
        },
        "backend.workers.tasks.extract_turn_memories_task": {
            "queue": settings.CELERY_MEMORY_QUEUE
        },
        "backend.workers.tasks.run_ai_generation_task": {"queue": settings.CELERY_AI_QUEUE},
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=settings.CELERY_RESULT_EXPIRES_SECONDS,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SECONDS,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "dispatch-background-job-outbox": {
            "task": "backend.workers.tasks.dispatch_outbox_task",
            "schedule": 30.0,
        },
        "cleanup-expired-chat-conversations": {
            "task": "backend.workers.tasks.cleanup_chat_retention_task",
            "schedule": 3600.0,
        },
    },
)

import backend.workers.logging_hooks  # noqa: F401,E402 — register Celery signal handlers
