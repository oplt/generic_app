from types import SimpleNamespace

from backend.modules.rag.application.document_identity import (
    content_fingerprint,
    display_filename,
    document_embedding_is_current,
    document_needs_reindex,
    embedding_metadata_matches,
)
from backend.modules.rag.application.document_ingestion_service import DocumentUploadResult
from backend.modules.rag.application.pipeline_versions import (
    CHUNKER_VERSION,
    EMBEDDING_SCHEMA_VERSION,
    PARSER_VERSION,
    pipeline_version_metadata,
)


def test_upload_identity_is_stable_and_filename_never_keeps_path():
    assert content_fingerprint(b"same") == content_fingerprint(b"same")
    assert content_fingerprint(b"same") != content_fingerprint(b"different")
    assert display_filename(r"../../private\report.pdf") == "report.pdf"


def test_embedding_metadata_detects_model_drift():
    expected = {
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
    }
    assert embedding_metadata_matches(expected, expected)
    assert not embedding_metadata_matches({**expected, "embedding_model": "old-model"}, expected)
    assert not embedding_metadata_matches({}, expected)


def test_pipeline_metadata_includes_parser_and_chunker_versions():
    config = SimpleNamespace(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )
    metadata = pipeline_version_metadata(config)
    assert metadata["parser_version"] == PARSER_VERSION
    assert metadata["chunker_version"] == CHUNKER_VERSION
    assert metadata["embedding_schema_version"] == EMBEDDING_SCHEMA_VERSION
    assert metadata["embedding_model"] == "text-embedding-3-small"
    assert metadata["chunking_mode"] == "basic"
    assert metadata["index_version"].startswith("idx-")
    assert document_embedding_is_current(metadata, config)
    assert not document_needs_reindex(metadata, config)


def test_stale_parser_or_chunker_version_requires_reindex():
    config = SimpleNamespace(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )
    metadata = pipeline_version_metadata(config)
    stale_parser = {**metadata, "parser_version": "parser-v0"}
    stale_chunker = {**metadata, "chunker_version": "chunker-v0"}
    assert not document_embedding_is_current(stale_parser, config)
    assert document_needs_reindex(stale_chunker, config)
    assert document_needs_reindex({}, config)


def test_upload_result_preserves_legacy_two_value_unpacking():
    result = DocumentUploadResult(SimpleNamespace(id="doc"), SimpleNamespace(id="job"), True)
    document, job = result
    assert document.id == "doc"
    assert job.id == "job"
    assert result.duplicate is True
