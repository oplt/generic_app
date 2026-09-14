from __future__ import annotations

import logging

from backend.core.config import settings
from backend.workers.async_dispatch import dispatch_background_sync_job, run_async_in_sync_context

logger = logging.getLogger(__name__)


def run_ai_generation_sync(**kwargs) -> None:
    from backend.db.session import SessionLocal
    from backend.modules.ai.run_service import AiRunService
    from backend.modules.identity_access.repository import IdentityRepository

    async def _run() -> None:
        async with SessionLocal() as db:
            user = await IdentityRepository(db).get_user_by_id(kwargs["user_id"])
            if user is None:
                raise ValueError("AI generation user no longer exists")
            run_kwargs = {key: value for key, value in kwargs.items() if key != "user_id"}
            await AiRunService(db).run_prompt(user, **run_kwargs)

    run_async_in_sync_context(_run())


def queue_ai_generation(**kwargs) -> None:
    from backend.workers.tasks import run_ai_generation_task

    dispatch_background_sync_job(
        target=run_ai_generation_sync,
        kwargs=kwargs,
        celery_task=run_ai_generation_task,
        celery_kwargs=kwargs,
        queue=settings.CELERY_AI_QUEUE,
        job_name="ai-generation",
    )
    logger.info("Queued async AI generation user=%s", kwargs["user_id"])
