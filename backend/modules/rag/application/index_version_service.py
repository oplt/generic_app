"""RAG index version lifecycle and blue/green reindex workflows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from backend.core.config import settings
from backend.lib.retrieval_cache import bump_corpus_generation
from backend.modules.rag.application.document_ingestion_service import DocumentIngestionService
from backend.modules.rag.application.pipeline_versions import (
    INDEX_VERSION_STATUSES,
    index_version_key,
    pipeline_snapshot_from_row,
    pipeline_version_metadata,
)
from backend.modules.rag.infrastructure.models import (
    RAG_VECTOR_DIMENSIONS,
    RagChunk,
    RagDocument,
    RagIndexVersion,
    RagIngestionJob,
)
from backend.modules.rag.infrastructure.rag_config import RagConfig
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Explicit lifecycle edges. Activation from building is forbidden.
_ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("building", "validated"),
        ("validated", "active"),
        ("active", "retired"),
        ("retired", "active"),  # rollback only
    }
)


class IndexVersionService:
    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()

    async def get_active_version(self) -> RagIndexVersion | None:
        result = await self.db.execute(
            select(RagIndexVersion).where(RagIndexVersion.status == "active").limit(1)
        )
        return result.scalar_one_or_none()

    async def ensure_active_version(self) -> RagIndexVersion:
        """Return the serving (active) index version.

        Cold-start only creates a validated+active row when the table is empty.
        Config drift never auto-promotes a candidate; it opens/keeps a building row.
        """

        active = await self.get_active_version()
        if active is not None:
            await self.ensure_desired_building_version()
            return active

        metadata = pipeline_version_metadata(self.config)
        key = str(metadata["index_version"])
        existing = await self.get_by_key(key)
        if existing is not None:
            if existing.status == "active":
                return existing
            raise HTTPException(
                status_code=409,
                detail=(
                    "No active RAG index version. Validate and activate a candidate "
                    f"(desired key={key!r}, found status={existing.status!r})."
                ),
            )

        self._assert_dimensions_compatible(int(metadata["embedding_dimensions"]))
        row = RagIndexVersion(
            key=key,
            status="active",
            parser_version=str(metadata["parser_version"]),
            chunker_version=str(metadata["chunker_version"]),
            embedding_schema_version=str(metadata["embedding_schema_version"]),
            embedding_provider=str(metadata["embedding_provider"]),
            embedding_model=str(metadata["embedding_model"]),
            embedding_dimensions=int(metadata["embedding_dimensions"]),
            notes="Bootstrap active version from runtime RAG configuration.",
            activated_at=datetime.now(UTC),
            validated_at=datetime.now(UTC),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def ensure_desired_building_version(self) -> RagIndexVersion | None:
        """When runtime config differs from active, ensure a building candidate."""

        active = await self.get_active_version()
        metadata = pipeline_version_metadata(self.config)
        desired_key = str(metadata["index_version"])
        if active is not None and active.key == desired_key:
            return None
        existing = await self.get_by_key(desired_key)
        if existing is not None:
            return existing
        self._assert_dimensions_compatible(int(metadata["embedding_dimensions"]))
        row = RagIndexVersion(
            key=desired_key,
            status="building",
            parser_version=str(metadata["parser_version"]),
            chunker_version=str(metadata["chunker_version"]),
            embedding_schema_version=str(metadata["embedding_schema_version"]),
            embedding_provider=str(metadata["embedding_provider"]),
            embedding_model=str(metadata["embedding_model"]),
            embedding_dimensions=int(metadata["embedding_dimensions"]),
            notes="Auto-opened building candidate because runtime config differs from active.",
        )
        self.db.add(row)
        await self.db.flush()
        logger.info(
            "Opened building index version key=%s while active=%s",
            desired_key,
            getattr(active, "key", None),
        )
        return row

    async def resolve_write_version(self) -> RagIndexVersion:
        """Version that new chunk writes target (building desired, else active)."""

        metadata = pipeline_version_metadata(self.config)
        desired_key = str(metadata["index_version"])
        desired = await self.get_by_key(desired_key)
        if desired is not None and desired.status in {"building", "validated", "active"}:
            return desired
        return await self.ensure_active_version()

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
        row = await self._lock_version(version_id)
        if row.status == "validated":
            return row
        self._assert_transition(row.status, "validated")
        readiness = await self.promotion_readiness(row)
        if not readiness["ready_for_validation"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Index version is not ready for validation",
                    "readiness": readiness,
                },
            )
        row.status = "validated"
        row.validated_at = datetime.now(UTC)
        await self.db.flush()
        return row

    async def activate(self, version_id: str) -> RagIndexVersion:
        """Promote a validated candidate. Never activates building versions."""

        row = await self._lock_version(version_id)
        if row.status == "active":
            return row
        self._assert_transition(row.status, "active")
        if row.status != "validated" or row.validated_at is None:
            raise HTTPException(
                status_code=422,
                detail="Only validated index versions can be activated",
            )
        readiness = await self.promotion_readiness(row)
        if not readiness["ready_for_activation"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Index version failed promotion criteria",
                    "readiness": readiness,
                },
            )
        await self._retire_other_active(except_id=row.id)
        now = datetime.now(UTC)
        row.status = "active"
        row.activated_at = now
        row.retired_at = None
        await self.db.flush()
        try:
            await bump_corpus_generation(organization_id=None, project_id=None)
        except Exception:
            logger.exception("Failed to bump retrieval corpus generation after activation")
        return row

    async def rollback(self, version_id: str) -> RagIndexVersion:
        """Re-activate a retired version without re-embedding."""

        row = await self._lock_version(version_id)
        if row.status == "active":
            return row
        if row.status != "retired":
            raise HTTPException(
                status_code=422,
                detail=f"Rollback requires a retired version (got {row.status!r})",
            )
        self._assert_dimensions_compatible(row.embedding_dimensions)
        chunk_count = await self._count_chunks_for_version(row.id)
        if chunk_count < 1:
            raise HTTPException(
                status_code=422,
                detail="Cannot rollback to a version with no remaining chunks",
            )
        await self._retire_other_active(except_id=row.id)
        now = datetime.now(UTC)
        row.status = "active"
        row.activated_at = now
        row.retired_at = None
        await self.db.flush()
        try:
            await bump_corpus_generation(organization_id=None, project_id=None)
        except Exception:
            logger.exception("Failed to bump retrieval corpus generation after rollback")
        return row

    async def promotion_readiness(self, row: RagIndexVersion) -> dict[str, object]:
        documents_total = await self._count_documents()
        documents_indexed = await self._count_documents(status="indexed")
        docs_with_chunks = await self._count_documents_with_chunks(row.id)
        chunk_count = await self._count_chunks_for_version(row.id)
        jobs_failed = await self._count_jobs(status="failed")
        jobs_active = await self._count_jobs(active_only=True)
        coverage = (
            (docs_with_chunks / documents_indexed) if documents_indexed > 0 else 1.0
        )
        min_coverage = float(settings.RAG_INDEX_ACTIVATION_MIN_DOC_COVERAGE)
        max_failed = int(settings.RAG_INDEX_ACTIVATION_MAX_FAILED_JOBS)
        dimension_ok = row.embedding_dimensions == RAG_VECTOR_DIMENSIONS
        has_chunks = chunk_count > 0 or documents_indexed == 0
        coverage_ok = coverage >= min_coverage
        failed_ok = jobs_failed <= max_failed
        ready_for_validation = dimension_ok and has_chunks
        ready_for_activation = (
            dimension_ok
            and has_chunks
            and coverage_ok
            and failed_ok
            and jobs_active == 0
            and row.validated_at is not None
        )
        return {
            "version_id": row.id,
            "version_key": row.key,
            "status": row.status,
            "documents_total": documents_total,
            "documents_indexed": documents_indexed,
            "documents_with_chunks": docs_with_chunks,
            "documents_incomplete": max(documents_indexed - docs_with_chunks, 0),
            "chunk_count": chunk_count,
            "coverage": round(coverage, 4),
            "min_coverage": min_coverage,
            "jobs_active": jobs_active,
            "jobs_failed": jobs_failed,
            "max_failed_jobs": max_failed,
            "dimension_ok": dimension_ok,
            "ready_for_validation": ready_for_validation,
            "ready_for_activation": ready_for_activation,
        }

    async def status_summary(self) -> dict[str, object]:
        active = await self.ensure_active_version()
        desired = pipeline_version_metadata(self.config)
        building = await self.get_by_key(str(desired["index_version"]))
        if building is not None and (
            building.id == active.id or building.status not in {"building", "validated"}
        ):
            building = None
        snapshot = pipeline_snapshot_from_row(active)
        documents_total = await self._count_documents()
        documents_indexed = await self._count_documents(status="indexed")
        documents_current = await self._count_documents_with_chunks(active.id)
        documents_stale = max(documents_indexed - documents_current, 0)
        jobs_active = await self._count_jobs(active_only=True)
        jobs_failed = await self._count_jobs(status="failed")
        versions = await self.list_versions()
        building_readiness = (
            await self.promotion_readiness(building) if building is not None else None
        )
        return {
            "active_version": active,
            "desired_index_version": desired["index_version"],
            "building_version": building,
            "building_readiness": building_readiness,
            "pipeline": snapshot,
            "schema_embedding_dimensions": RAG_VECTOR_DIMENSIONS,
            "documents_total": documents_total,
            "documents_indexed": documents_indexed,
            "documents_current": documents_current,
            "documents_stale": documents_stale,
            "documents_incomplete": documents_stale,
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
        """Enqueue side-by-side indexing into the write target version."""

        target = await self.resolve_write_version()
        self._assert_dimensions_compatible(target.embedding_dimensions)
        missing = await self._list_documents_missing_version(target.id, limit=limit)
        ingestion = DocumentIngestionService(self.db, config=self.config)
        enqueued = 0
        skipped = 0
        job_ids: list[str] = []
        for document_id, owner_id in missing:
            job = await ingestion.enqueue_document_indexing(
                document_id=document_id,
                user_id=owner_id or actor_user_id,
                is_admin=True,
                force_new_attempt=False,
            )
            enqueued += 1
            job_ids.append(job.id)
        active = await self.get_active_version()
        return {
            "requested": len(missing),
            "enqueued": enqueued,
            "skipped": skipped,
            "job_ids": job_ids,
            "active_index_version": active.key if active is not None else target.key,
            "target_index_version": target.key,
            "target_index_version_id": target.id,
        }

    async def cleanup_retired_versions(self) -> dict[str, int]:
        """Delete chunks for retired versions past retention; keep version rows."""

        retention_days = int(settings.RAG_INDEX_RETENTION_DAYS)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self.db.execute(
            select(RagIndexVersion).where(
                RagIndexVersion.status == "retired",
                RagIndexVersion.retired_at.is_not(None),
                RagIndexVersion.retired_at < cutoff,
            )
        )
        versions = list(result.scalars().all())
        deleted_chunks = 0
        for version in versions:
            chunk_result = await self.db.execute(
                delete(RagChunk).where(RagChunk.index_version_id == version.id)
            )
            deleted_chunks += int(chunk_result.rowcount or 0)
        await self.db.commit()
        return {"versions_considered": len(versions), "chunks_deleted": deleted_chunks}

    async def _lock_version(self, version_id: str) -> RagIndexVersion:
        result = await self.db.execute(
            select(RagIndexVersion)
            .where(RagIndexVersion.id == version_id)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Index version not found")
        await self.db.execute(
            select(RagIndexVersion.id)
            .where(RagIndexVersion.status == "active")
            .with_for_update()
        )
        return row

    async def _retire_other_active(self, *, except_id: str | None) -> None:
        result = await self.db.execute(
            select(RagIndexVersion)
            .where(RagIndexVersion.status == "active")
            .with_for_update()
        )
        now = datetime.now(UTC)
        for row in result.scalars().all():
            if except_id is not None and row.id == except_id:
                continue
            self._assert_transition(row.status, "retired")
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

    async def _count_chunks_for_version(self, version_id: str) -> int:
        stmt = select(func.count()).select_from(RagChunk).where(
            RagChunk.index_version_id == version_id
        )
        return int(await self.db.scalar(stmt) or 0)

    async def _count_documents_with_chunks(self, version_id: str) -> int:
        stmt = (
            select(func.count(func.distinct(RagChunk.document_id)))
            .select_from(RagChunk)
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .where(
                RagChunk.index_version_id == version_id,
                RagDocument.deleted_at.is_(None),
                RagDocument.status == "indexed",
            )
        )
        return int(await self.db.scalar(stmt) or 0)

    async def _list_documents_missing_version(
        self, version_id: str, *, limit: int
    ) -> list[tuple[str, str]]:
        sql = text(
            """
            SELECT d.id, d.user_id
            FROM rag_documents d
            WHERE d.deleted_at IS NULL
              AND d.status = 'indexed'
              AND NOT EXISTS (
                SELECT 1 FROM rag_chunks c
                WHERE c.document_id = d.id
                  AND c.index_version_id = :version_id
              )
            ORDER BY d.updated_at ASC
            LIMIT :limit
            """
        )
        result = await self.db.execute(sql, {"version_id": version_id, "limit": limit})
        return [(str(row[0]), str(row[1])) for row in result.all()]

    @staticmethod
    def _assert_transition(current: str, target: str) -> None:
        if (current, target) not in _ALLOWED_TRANSITIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid index version transition {current!r} -> {target!r}",
            )

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


__all__ = [
    "IndexVersionService",
    "assert_valid_status",
    "index_version_key",
]
