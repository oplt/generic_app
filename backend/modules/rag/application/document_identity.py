from __future__ import annotations

import hashlib
import re
from typing import Any


def content_fingerprint(content: bytes) -> str:
    """Return a stable, bounded identity for exact-content deduplication."""

    return hashlib.sha256(content).hexdigest()


def display_filename(filename: str | None) -> str:
    """Normalize untrusted upload names for display metadata only."""

    raw = str(filename or "upload.bin").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "upload.bin")[:512]


def embedding_metadata_matches(metadata: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Detect vectors created with a different embedding configuration."""

    return all(metadata.get(key) == value for key, value in expected.items())


def document_embedding_is_current(metadata: dict[str, Any], config: Any) -> bool:
    return embedding_metadata_matches(
        metadata,
        {
            "embedding_provider": config.embedding_provider,
            "embedding_model": config.embedding_model,
            "embedding_dimensions": config.embedding_dimensions,
        },
    )
