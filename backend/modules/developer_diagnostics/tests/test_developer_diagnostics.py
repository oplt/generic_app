"""Tests for developer diagnostics mode."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.observability.request_diagnostics import (
    RequestDiagnostics,
    begin_request,
    clear_recent,
    finish_request,
    is_enabled,
    recent_snapshots,
    record_cache_hit,
    record_cache_miss,
    record_celery_task,
    record_external_call,
    record_rag_chunks,
    record_rag_stage,
)


class DeveloperDiagnosticsFlagTest(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        with patch(
            "backend.observability.request_diagnostics.settings"
        ) as mock_settings:
            mock_settings.DEVELOPER_DIAGNOSTICS_ENABLED = False
            self.assertFalse(is_enabled())

    def test_begin_is_noop_when_disabled(self) -> None:
        clear_recent()
        with patch(
            "backend.observability.request_diagnostics.settings"
        ) as mock_settings:
            mock_settings.DEVELOPER_DIAGNOSTICS_ENABLED = False
            token = begin_request(method="GET", path="/api/v1/x", correlation_id="c1")
            self.assertIsNone(token)
            record_cache_hit()
            self.assertEqual(recent_snapshots(), [])


class DeveloperDiagnosticsCollectorTest(unittest.TestCase):
    def setUp(self) -> None:
        clear_recent()

    def test_collects_safe_summary_without_bodies(self) -> None:
        with patch(
            "backend.observability.request_diagnostics.settings"
        ) as mock_settings:
            mock_settings.DEVELOPER_DIAGNOSTICS_ENABLED = True
            token = begin_request(method="GET", path="/api/v1/rag/retrieve", correlation_id="abc")
            self.assertIsNotNone(token)
            record_cache_hit()
            record_cache_miss()
            record_external_call(provider="openai", operation="embed", latency_ms=12.5)
            record_celery_task("rag-indexing")
            record_rag_stage("strategy:hybrid_rrf")
            record_rag_chunks(3)
            summary = finish_request(token, status_code=200, duration_ms=42.0)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["cache_hits"], 1)
        self.assertEqual(summary["cache_misses"], 1)
        self.assertEqual(summary["rag_retrieved_chunk_count"], 3)
        self.assertEqual(summary["celery_tasks"], ["rag-indexing"])
        blob = str(summary)
        self.assertNotIn("password", blob.lower())
        self.assertNotIn("Bearer", blob)
        self.assertNotIn("SELECT", blob)
        self.assertEqual(recent_snapshots(limit=1)[0]["correlation_id"], "abc")

    def test_public_dict_omits_internal_timer(self) -> None:
        snap = RequestDiagnostics(method="GET", path="/x")
        snap._db_timer_start = 1.23
        payload = snap.to_public_dict()
        self.assertNotIn("_db_timer_start", payload)
