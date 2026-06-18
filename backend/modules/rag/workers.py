from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.core.config import settings

logger = logging.getLogger(__name__)

_pending_content: dict[str, bytes] = {}


def store_pending_content(document_id: str, content: bytes) -> None:
    _pending_content[document_id] = content


def get_pending_content(document_id: str) -> bytes | None:
    return _pending_content.get(document_id)


def pop_pending_content(document_id: str) -> bytes | None:
    return _pending_content.pop(document_id, None)


def index_document_sync(*, document_id: str, user_id: str, content: bytes | None = None) -> None:
    from backend.db.session import SessionLocal
    from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService

    async def _run() -> None:
        async with SessionLocal() as db:
            service = DocumentIngestionService(db)
            file_content = content or pop_pending_content(document_id)
            await service.index_document(
                document_id=document_id,
                user_id=user_id,
                file_content=file_content,
            )

    asyncio.run(_run())


def queue_document_indexing(
    *,
    document_id: str,
    user_id: str,
    content: bytes | None = None,
) -> None:
    if content is not None:
        store_pending_content(document_id, content)

    payload: dict[str, Any] = {"document_id": document_id, "user_id": user_id}
    if settings.CELERY_TASK_ALWAYS_EAGER:
        index_document_sync(document_id=document_id, user_id=user_id, content=content)
        return

    from backend.workers.tasks import index_rag_document_task

    index_rag_document_task.apply_async(kwargs=payload, queue=settings.CELERY_TASK_DEFAULT_QUEUE)
