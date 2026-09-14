"""RAG index version lifecycle and stale-document reindex workflows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService
from backend.modules.rag.application.pipeline_versions import (
    INDEX_VERSION_STATUSES,
    index_version_key,
    pipeline_snapshot_from_row,
    pipeline_version_metadata,
)
from backend.modules.rag.infrastructure.models import (
    RAG_VECTOR_DIMENSIONS,
    RagDocument,
    RagIndexVersion,
    RagIngestionJob,
)
from backend.modules.rag.infrastructure.rag_config import RagConfig
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class IndexVersionService:
    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()

    async def ensure_active_version(self) -> RagIndexVersion:
        """Create or refresh the active index version for the running config."""

        metadata = pipeline_version_metadata(self.config)
        key = str(metadata["index_version"])
        existing = await self.get_by_key(key)
        if existing is not None:
            if existing.status != "active":
                await self._retire_other_active(except_id=existing.id)
                existing.status = "active"
                existing.activated_at = datetime.now(UTC)
                existing.retired_at = None
                if existing.validated_at is None:
                    existing.validated_at = datetime.now(UTC)
                await self.db.flush()
            return existing

        self._assert_dimensions_compatible(int(metadata["embedding_dimensions"]))
        await self._retire_other_active(except_id=None)
        row = RagIndexVersion(
            key=key,
            status="active",
            parser_version=str(metadata["parser_version"]),
            chunker_version=str(metadata["chunker_version"]),
            embedding_schema_version=str(metadata["embedding_schema_version"]),
            embedding_provider=str(metadata["embedding_provider"]),
            embedding_model=str(metadata["embedding_model"]),
            embedding_dimensions=int(metadata["embedding_dimensions"]),
            notes="Auto-created from runtime RAG configuration.",
            activated_at=datetime.now(UTC),
            validated_at=datetime.now(UTC),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_versions(self) -> list[RagIndexVersion]:
        result = await self.db.execute(
            select(RagIndexVersion).order_by(RagIndexVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_key(self, key: str) -> RagIndexVersion | None:
        result = await self.db.execute(select(RagIndexVersion).where(RagIndexVersion.key == key))
        return result.scalar_one_or_none()

    async def get_by_id(self, version_id: str) -> RagIndexVersion | None:
        return await self.db.get(RagIndexVersion, version_id)

    async def create_building_version(self, *, notes: str | None = None) -> RagIndexVersion:
        metadata = pipeline_version_metadata(self.config)
        self._assert_dimensions_compatible(int(metadata["embedding_dimensions"]))
        key = str(metadata["index_version"])
        existing = await self.get_by_key(key)
        if existing is not None:
            return existing
        row = RagIndexVersion(
            key=key,
            status="building",
            parser_version=str(metadata["parser_version"]),
            chunker_version=str(metadata["chunker_version"]),
            embedding_schema_version=str(metadata["embedding_schema_version"]),
            embedding_provider=str(metadata["embedding_provider"]),
            embedding_model=str(metadata["embedding_model"]),
            embedding_dimensions=int(metadata["embedding_dimensions"]),
            notes=notes,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def mark_validated(self, version_id: str) -> RagIndexVersion:
        row = await self.get_by_id(version_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Index version not found")
        if row.status not in {"building", "validated"}:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot validate index version in status {row.status!r}",
            )
        row.status = "validated"
        row.validated_at = datetime.now(UTC)
        await self.db.flush()
        return row

    async def activate(self, version_id: str) -> RagIndexVersion:
        row = await self.get_by_id(version_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Index version not found")
        if row.status not in {"building", "validated", "active"}:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot activate index version in status {row.status!r}",
            )
        self._assert_dimensions_compatible(row.embedding_dimensions)
        await self._retire_other_active(except_id=row.id)
        now = datetime.now(UTC)
        row.status = "active"
        row.activated_at = now
        row.retired_at = None
        if row.validated_at is None:
            row.validated_at = now
        await self.db.flush()
        return row

    async def status_summary(self) -> dict[str, object]:
        active = await self.ensure_active_version()
        snapshot = pipeline_snapshot_from_row(active)
        documents_total = await self._count_documents()
        documents_indexed = await self._count_documents(status="indexed")
        documents_stale = await self._count_stale_indexed(snapshot)
        jobs_active = await self._count_jobs(active_only=True)
        jobs_failed = await self._count_jobs(status="failed")
        versions = await self.list_versions()
        return {
            "active_version": active,
            "pipeline": snapshot,
            "schema_embedding_dimensions": RAG_VECTOR_DIMENSIONS,
            "documents_total": documents_total,
            "documents_indexed": documents_indexed,
            "documents_current": max(documents_indexed - documents_stale, 0),
            "documents_stale": documents_stale,
            "jobs_active": jobs_active,
            "jobs_failed": jobs_failed,
            "versions": versions,
            "dimension_migration_required": active.embedding_dimensions != RAG_VECTOR_DIMENSIONS,
        }

    async def enqueue_stale_reindex(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
    ) -> dict[str, object]:
        """Non-destructively enqueue reindex jobs for stale indexed documents.

        Reuses the existing embedding column when dimensions match the pgvector
        schema. Documents are rebuilt in place (chunks replaced on successful
        ingestion) rather than dropping the prior index version first.
        """

        active = await self.ensure_active_version()
        self._assert_dimensions_compatible(active.embedding_dimensions)
        snapshot = pipeline_snapshot_from_row(active)
        stale_ids = await self._list_stale_document_ids(snapshot, limit=limit)
        ingestion = DocumentIngestionService(self.db, config=self.config)
        enqueued = 0
        skipped = 0
        job_ids: list[str] = []
        for document_id, owner_id in stale_ids:
            job = await ingestion.enqueue_document_indexing(
                document_id=document_id,
                user_id=owner_id or actor_user_id,
                is_admin=True,
                force_new_attempt=False,
            )
            enqueued += 1
            job_ids.append(job.id)
        return {
            "requested": len(stale_ids),
            "enqueued": enqueued,
            "skipped": skipped,
            "job_ids": job_ids,
            "active_index_version": active.key,
        }

    async def _retire_other_active(self, *, except_id: str | None) -> None:
        result = await self.db.execute(
            select(RagIndexVersion).where(RagIndexVersion.status == "active")
        )
        now = datetime.now(UTC)
        for row in result.scalars().all():
            if except_id is not None and row.id == except_id:
                continue
            row.status = "retired"
            row.retired_at = now

    async def _count_documents(self, *, status: str | None = None) -> int:
        stmt = select(func.count()).select_from(RagDocument).where(RagDocument.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(RagDocument.status == status)
        return int(await self.db.scalar(stmt) or 0)

    async def _count_jobs(self, *, status: str | None = None, active_only: bool = False) -> int:
        stmt = select(func.count()).select_from(RagIngestionJob)
        if active_only:
            stmt = stmt.where(RagIngestionJob.status.in_(("pending", "queued", "running")))
        elif status is not None:
            stmt = stmt.where(RagIngestionJob.status == status)
        return int(await self.db.scalar(stmt) or 0)

    def _stale_predicate_sql(self, snapshot: dict[str, object]) -> tuple[str, dict[str, object]]:
        clauses = []
        params: dict[str, object] = {}
        for key in (
            "parser_version",
            "chunker_version",
            "embedding_schema_version",
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
            "index_version",
        ):
            param = f"p_{key}"
            clauses.append(
                f"(metadata_json::jsonb->>'{key}') IS DISTINCT FROM CAST(:{param} AS TEXT)"
            )
            params[param] = str(snapshot.get(key))
        return " OR ".join(clauses), params

    async def _count_stale_indexed(self, snapshot: dict[str, object]) -> int:
        where_sql, params = self._stale_predicate_sql(snapshot)
        sql = text(
            f"""
            SELECT count(*) FROM rag_documents
            WHERE deleted_at IS NULL
              AND status = 'indexed'
              AND ({where_sql})
            """
        )
        result = await self.db.execute(sql, params)
        return int(result.scalar_one() or 0)

    async def _list_stale_document_ids(
        self, snapshot: dict[str, object], *, limit: int
    ) -> list[tuple[str, str]]:
        where_sql, params = self._stale_predicate_sql(snapshot)
        params = {**params, "limit": limit}
        sql = text(
            f"""
            SELECT id, user_id FROM rag_documents
            WHERE deleted_at IS NULL
              AND status = 'indexed'
              AND ({where_sql})
            ORDER BY updated_at ASC
            LIMIT :limit
            """
        )
        result = await self.db.execute(sql, params)
        return [(str(row[0]), str(row[1])) for row in result.all()]

    @staticmethod
    def _assert_dimensions_compatible(dimensions: int) -> None:
        if dimensions != RAG_VECTOR_DIMENSIONS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Embedding dimensions {dimensions} are incompatible with the "
                    f"pgvector column ({RAG_VECTOR_DIMENSIONS}). Create an Alembic "
                    "migration to change the vector schema before activating this "
                    "index version."
                ),
            )


def assert_valid_status(status: str) -> None:
    if status not in INDEX_VERSION_STATUSES:
        raise ValueError(f"Invalid index version status: {status}")


# Re-export for callers that only need the fingerprint helper.
__all__ = [
    "IndexVersionService",
    "assert_valid_status",
    "index_version_key",
]
