"""Tests for RAG index version lifecycle helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from backend.modules.rag.application.index_version_service import IndexVersionService
from backend.modules.rag.application.pipeline_versions import (
    index_version_key,
    pipeline_version_metadata,
)
from backend.modules.rag.infrastructure.models import RAG_VECTOR_DIMENSIONS


class PipelineIndexVersionTest(unittest.TestCase):
    def test_index_version_key_is_stable(self) -> None:
        config = SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
        )
        first = pipeline_version_metadata(config)
        second = pipeline_version_metadata(config)
        self.assertEqual(first["index_version"], second["index_version"])
        self.assertEqual(
            first["index_version"],
            index_version_key({k: first[k] for k in first if k != "index_version"}),
        )

    def test_dimension_mismatch_rejected(self) -> None:
        service = IndexVersionService(AsyncMock(), config=SimpleNamespace())
        with self.assertRaises(HTTPException) as ctx:
            service._assert_dimensions_compatible(RAG_VECTOR_DIMENSIONS + 1)
        self.assertEqual(ctx.exception.status_code, 422)


class IndexVersionServiceLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_activate_retires_previous_active(self) -> None:
        db = AsyncMock()
        config = SimpleNamespace(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
        )
        service = IndexVersionService(db, config=config)
        previous = SimpleNamespace(
            id="v1",
            status="active",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            retired_at=None,
        )
        target = SimpleNamespace(
            id="v2",
            status="validated",
            embedding_dimensions=RAG_VECTOR_DIMENSIONS,
            activated_at=None,
            retired_at=None,
            validated_at=None,
        )

        async def get_by_id(version_id: str):
            return target if version_id == "v2" else None

        service.get_by_id = get_by_id  # type: ignore[method-assign]
        service._retire_other_active = AsyncMock()  # type: ignore[method-assign]
        db.flush = AsyncMock()

        activated = await service.activate("v2")
        self.assertEqual(activated.status, "active")
        self.assertIsNotNone(activated.activated_at)
        service._retire_other_active.assert_awaited_once_with(except_id="v2")
        _ = previous
