from celery import Celery

from backend.core.config import settings
from backend.core.logging import setup_logging
from backend.modules.manifests.celery_contrib import (
    celery_include_modules,
    celery_runtime_for_profile,
)

setup_logging()

_resolution, _task_routes, _beat_schedule = celery_runtime_for_profile()

celery_app = Celery(
    "app_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=celery_include_modules(_resolution.active_modules),
)

celery_app.conf.update(
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_routes=_task_routes,
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
    beat_schedule=_beat_schedule,
)

# Expose resolved profile for diagnostics/tests.
celery_app.conf.capability_profile = _resolution.profile_key
celery_app.conf.active_modules = list(_resolution.active_modules)
celery_app.conf.active_celery_queues = list(_resolution.celery_queues)

import backend.workers.logging_hooks  # noqa: F401,E402 — register Celery signal handlers
