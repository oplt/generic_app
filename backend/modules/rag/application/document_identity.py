from __future__ import annotations

import hashlib
import re
from typing import Any

from backend.modules.rag.application.pipeline_versions import (
    document_pipeline_is_current,
    pipeline_version_metadata,
)


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
    return document_pipeline_is_current(metadata, config)


def document_needs_reindex(metadata: dict[str, Any], config: Any) -> bool:
    """True when parser/chunker/embedding versions no longer match the runtime."""

    return not document_pipeline_is_current(metadata, config)


def current_pipeline_metadata(config: Any) -> dict[str, object]:
    return pipeline_version_metadata(config)
