"""Version stamps for RAG parse/chunk/embed pipelines and index lifecycle."""

from __future__ import annotations

import hashlib
from typing import Any

# Bump these when the corresponding algorithm or durable schema changes.
PARSER_VERSION = "parser-v1"
CHUNKER_VERSION = "chunker-v3"
EMBEDDING_SCHEMA_VERSION = "embedding-schema-v1"

PIPELINE_VERSION_KEYS = (
    "parser_version",
    "chunker_version",
    "embedding_schema_version",
    "embedding_provider",
    "embedding_model",
    "embedding_dimensions",
    "chunking_mode",
)

INDEX_VERSION_STATUSES = (
    "building",
    "validated",
    "active",
    "retired",
)


def pipeline_version_metadata(config: Any) -> dict[str, object]:
    """Return durable version fields stored on documents and chunks."""

    document_aware = bool(getattr(config, "document_aware_chunking", False))
    parent_child = bool(getattr(config, "parent_child_chunking", False))
    values = {
        "parser_version": PARSER_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "embedding_schema_version": EMBEDDING_SCHEMA_VERSION,
        "embedding_provider": getattr(config, "embedding_provider", None),
        "embedding_model": getattr(config, "embedding_model", None),
        "embedding_dimensions": getattr(config, "embedding_dimensions", None),
        "chunking_mode": (
            "parent_child"
            if parent_child
            else ("document_aware" if document_aware else "basic")
        ),
    }
    metadata = {
        key: value
        for key, value in values.items()
        if isinstance(value, (str, int, float)) and not isinstance(value, bool)
    }
    metadata["index_version"] = index_version_key(metadata)
    return metadata


def index_version_key(pipeline: dict[str, object]) -> str:
    """Deterministic short key for a pipeline configuration fingerprint."""

    parts = [f"{key}={pipeline.get(key)}" for key in PIPELINE_VERSION_KEYS]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"idx-{digest[:12]}"


def pipeline_cache_variant_suffix() -> str:
    """Include algorithm versions in retrieval cache variants."""

    return f"{PARSER_VERSION}:{CHUNKER_VERSION}:{EMBEDDING_SCHEMA_VERSION}"


def document_pipeline_is_current(metadata: dict[str, Any], config: Any) -> bool:
    """True when stored document metadata matches the running pipeline versions."""

    expected = pipeline_version_metadata(config)
    return all(metadata.get(key) == value for key, value in expected.items())


def pipeline_snapshot_from_row(row: Any) -> dict[str, object]:
    """Normalize an index-version ORM row (or mapping) into pipeline metadata."""

    values = {
        "parser_version": getattr(row, "parser_version", None),
        "chunker_version": getattr(row, "chunker_version", None),
        "embedding_schema_version": getattr(row, "embedding_schema_version", None),
        "embedding_provider": getattr(row, "embedding_provider", None),
        "embedding_model": getattr(row, "embedding_model", None),
        "embedding_dimensions": getattr(row, "embedding_dimensions", None),
        "index_version": getattr(row, "key", None),
    }
    return {
        key: value
        for key, value in values.items()
        if isinstance(value, (str, int, float)) and not isinstance(value, bool)
    }
