from __future__ import annotations

import logging
from uuid import uuid4

from backend.core.storage import (
    PRIVATE_UPLOAD_CACHE_CONTROL,
    StorageNotConfiguredError,
    object_storage,
)

logger = logging.getLogger(__name__)


def build_document_object_key(
    user_id: str,
    filename: str | None = None,
    *,
    object_id: str | None = None,
) -> str:
    """Build an opaque key; the display filename never enters storage paths."""
    del filename
    return f"rag/{user_id}/{object_id or uuid4().hex}"


class FileStorageAdapter:
    async def store_document(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        object_key: str | None = None,
    ) -> str | None:
        if not object_storage.is_configured:
            logger.info("Object storage not configured; document kept in DB metadata only")
            return None
        object_key = object_key or build_document_object_key(user_id, filename)
        try:
            await object_storage.upload_bytes(
                object_key=object_key,
                body=content,
                content_type=content_type,
                cache_control=PRIVATE_UPLOAD_CACHE_CONTROL,
            )
            return object_key
        except StorageNotConfiguredError:
            return None

    async def delete_document(self, storage_path: str | None) -> None:
        if storage_path:
            await object_storage.delete_object(storage_path, raise_on_error=True)

    async def download_document(self, storage_path: str) -> bytes:
        if not object_storage.is_configured:
            raise StorageNotConfiguredError("Object storage is not configured")

        from backend.core.config import settings

        def _get() -> bytes:
            response = object_storage._client.get_object(  # noqa: SLF001
                Bucket=settings.STORAGE_BUCKET,
                Key=storage_path,
            )
            content_length = response.get("ContentLength")
            if isinstance(content_length, int) and content_length > settings.RAG_MAX_FILE_BYTES:
                raise ValueError("Stored document exceeds the configured size limit")
            body = response["Body"].read(settings.RAG_MAX_FILE_BYTES + 1)
            if len(body) > settings.RAG_MAX_FILE_BYTES:
                raise ValueError("Stored document exceeds the configured size limit")
            return body

        import asyncio

        return await asyncio.to_thread(_get)
