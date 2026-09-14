from types import SimpleNamespace

from backend.modules.rag.application.document_identity import (
    content_fingerprint,
    display_filename,
    embedding_metadata_matches,
)
from backend.modules.rag.application.document_ingestion_service import DocumentUploadResult


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


def test_upload_result_preserves_legacy_two_value_unpacking():
    result = DocumentUploadResult(SimpleNamespace(id="doc"), SimpleNamespace(id="job"), True)
    document, job = result
    assert document.id == "doc"
    assert job.id == "job"
    assert result.duplicate is True
