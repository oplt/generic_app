from __future__ import annotations

from tempfile import SpooledTemporaryFile

from fastapi import UploadFile


class UploadTooLargeError(ValueError):
    """Raised when an upload exceeds its configured byte budget."""


async def read_upload_limited(
    upload: UploadFile,
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> bytes:
    """Read upload with early length rejection and a capped spooled buffer."""
    if max_bytes < 1 or chunk_size < 1:
        raise ValueError("max_bytes and chunk_size must be positive")
    headers = getattr(upload, "headers", None)
    raw_content_length = headers.get("content-length") if headers else None
    if raw_content_length:
        try:
            content_length = int(raw_content_length)
        except (TypeError, ValueError):
            content_length = None
        if content_length is not None and content_length > max_bytes:
            raise UploadTooLargeError(f"Upload exceeds the maximum size of {max_bytes} bytes")

    total = 0
    with SpooledTemporaryFile(max_size=min(max_bytes, 1024 * 1024), mode="w+b") as spool:
        while True:
            chunk = await upload.read(min(chunk_size, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise UploadTooLargeError(f"Upload exceeds the maximum size of {max_bytes} bytes")
            spool.write(chunk)
        spool.seek(0)
        return spool.read()


def detect_image_content_type(content: bytes) -> str | None:
    """Return trusted MIME type for supported image signatures."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None
