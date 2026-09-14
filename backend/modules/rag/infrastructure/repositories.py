from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from backend.core.config import settings
from backend.core.pagination import DEFAULT_PAGE_LIMIT, paginate_cursor_scalars, paginate_scalars
from backend.lib.vector_search import (
    embedding_is_indexable,
    pgvector_readiness,
    reset_pgvector_readiness_cache,
    store_chunk_embeddings_batch,
)
from backend.lib.vectors import vector_literal
from backend.modules.rag.domain.enums import DocumentStatus, IngestionJobStatus
from backend.modules.rag.domain.models import RetrievedChunk
from backend.modules.rag.infrastructure.models import (
    RagChunk,
    RagDocument,
    RagIngestionJob,
    RagQueryRecord,
)
from backend.modules.rag.infrastructure.pgvector_errors import PgVectorUnavailableError
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RagRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document(
        self,
        *,
        user_id: str,
        filename: str,
        original_filename: str,
        content_type: str,
        content_fingerprint: str | None,
        storage_path: str | None,
        project_id: str | None,
        organization_id: str | None,
        source_type: str,
        metadata: dict | None,
    ) -> RagDocument:
        row = RagDocument(
            user_id=user_id,
            filename=filename,
            original_filename=original_filename,
            content_type=content_type,
            content_fingerprint=content_fingerprint,
            storage_path=storage_path,
            project_id=project_id,
            organization_id=organization_id,
            source_type=source_type,
            status=DocumentStatus.UPLOADED.value,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=True),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def find_document_by_fingerprint(
        self,
        *,
        user_id: str,
        project_id: str | None,
        fingerprint: str,
        organization_id: str | None = None,
    ) -> RagDocument | None:
        stmt = select(RagDocument).where(
            RagDocument.user_id == user_id,
            RagDocument.content_fingerprint == fingerprint,
            RagDocument.deleted_at.is_(None),
        )
        if project_id is None:
            stmt = stmt.where(RagDocument.project_id.is_(None))
        else:
            stmt = stmt.where(RagDocument.project_id == project_id)
        if organization_id is not None:
            stmt = stmt.where(RagDocument.organization_id == organization_id)
        stmt = stmt.order_by(RagDocument.updated_at.desc()).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_document(self, document_id: str) -> RagDocument | None:
        result = await self.db.execute(
            select(RagDocument).where(
                RagDocument.id == document_id,
                RagDocument.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_documents_for_user(
        self,
        user_id: str,
        *,
        project_id: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[RagDocument], int]:
        stmt = select(RagDocument).where(
            RagDocument.user_id == user_id,
            RagDocument.deleted_at.is_(None),
        )
        if project_id:
            stmt = stmt.where(RagDocument.project_id == project_id)
        stmt = stmt.order_by(RagDocument.created_at.desc())
        return await paginate_scalars(self.db, stmt, limit=limit, offset=offset)

    async def count_documents_for_user(self, user_id: str) -> int:
        return int(
            await self.db.scalar(
                select(func.count(RagDocument.id)).where(
                    RagDocument.user_id == user_id,
                    RagDocument.deleted_at.is_(None),
                )
            )
            or 0
        )

    async def list_documents_for_user_cursor(
        self, user_id: str, *, project_id: str | None, limit: int, cursor: str | None
    ) -> tuple[list[RagDocument], str | None, bool]:
        stmt = select(RagDocument).where(
            RagDocument.user_id == user_id, RagDocument.deleted_at.is_(None)
        )
        if project_id:
            stmt = stmt.where(RagDocument.project_id == project_id)
        return await paginate_cursor_scalars(
            self.db,
            stmt,
            limit=limit,
            cursor=cursor,
            sort_column=RagDocument.created_at,
            id_column=RagDocument.id,
        )

    async def list_document_ids_for_user(
        self,
        user_id: str,
        *,
        project_id: str | None = None,
    ) -> list[str]:
        stmt = select(RagDocument.id).where(
            RagDocument.user_id == user_id,
            RagDocument.deleted_at.is_(None),
        )
        if project_id:
            stmt = stmt.where(RagDocument.project_id == project_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def filter_document_ids_for_user(
        self,
        user_id: str,
        document_ids: list[str],
        *,
        project_id: str | None = None,
        organization_id: str | None = None,
    ) -> list[str]:
        if not document_ids:
            return []
        owner_scope = RagDocument.user_id == user_id
        if organization_id is not None:
            owner_scope = or_(owner_scope, RagDocument.organization_id == organization_id)
        stmt = select(RagDocument.id).where(
            owner_scope,
            RagDocument.deleted_at.is_(None),
            RagDocument.id.in_(document_ids),
        )
        if project_id:
            stmt = stmt.where(RagDocument.project_id == project_id)
        if organization_id is not None:
            stmt = stmt.where(RagDocument.organization_id == organization_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_indexed_documents(
        self,
        user_id: str,
        *,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
        organization_id: str | None = None,
    ) -> list[RagDocument]:
        owner_scope = RagDocument.user_id == user_id
        if organization_id is not None:
            owner_scope = or_(owner_scope, RagDocument.organization_id == organization_id)
        stmt = select(RagDocument).where(
            owner_scope,
            RagDocument.status == DocumentStatus.INDEXED.value,
            RagDocument.deleted_at.is_(None),
        )
        if project_id:
            stmt = stmt.where(RagDocument.project_id == project_id)
        if document_ids:
            stmt = stmt.where(RagDocument.id.in_(document_ids))
        if organization_id is not None:
            stmt = stmt.where(RagDocument.organization_id == organization_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_available_document_ids_for_chat(
        self,
        user_id: str,
        document_ids: list[str],
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> set[str]:
        if not document_ids:
            return set()
        owner_scope = RagDocument.user_id == user_id
        if organization_id is not None:
            owner_scope = or_(owner_scope, RagDocument.organization_id == organization_id)
        stmt = select(RagDocument.id).where(
            RagDocument.id.in_(document_ids),
            owner_scope,
            RagDocument.status == DocumentStatus.INDEXED.value,
            RagDocument.deleted_at.is_(None),
        )
        if project_id is not None:
            stmt = stmt.where(RagDocument.project_id == project_id)
        result = await self.db.execute(stmt)
        return set(result.scalars().all())

    async def update_document_status(
        self, document: RagDocument, status: DocumentStatus
    ) -> RagDocument:
        document.status = status.value
        document.updated_at = datetime.now(UTC)
        await self.db.flush()
        return document

    async def soft_delete_document(self, document: RagDocument) -> RagDocument:
        document.status = DocumentStatus.DELETED.value
        document.deleted_at = datetime.now(UTC)
        document.updated_at = datetime.now(UTC)
        await self.db.flush()
        return document

    async def replace_chunks(
        self,
        document: RagDocument,
        chunks: list[dict],
    ) -> list[RagChunk]:
        await self.db.execute(delete(RagChunk).where(RagChunk.document_id == document.id))
        rows: list[RagChunk] = []
        for item in chunks:
            row = RagChunk(
                document_id=document.id,
                user_id=document.user_id,
                organization_id=document.organization_id,
                project_id=document.project_id,
                chunk_index=item["chunk_index"],
                content=item["content"],
                token_count=item["token_count"],
                metadata_json=json.dumps(item.get("metadata", {}), ensure_ascii=True),
                vector_external_id=item.get("vector_external_id"),
            )
            self.db.add(row)
            rows.append(row)
        await self.db.flush()
        await store_chunk_embeddings_batch(
            self.db,
            table="rag_chunks",
            items=[
                (row.id, item.get("embedding") or [])
                for row, item in zip(rows, chunks, strict=True)
            ],
        )
        await self.db.flush()
        return rows

    async def delete_chunks_for_document(self, document_id: str) -> None:
        await self.db.execute(delete(RagChunk).where(RagChunk.document_id == document_id))

    async def delete_query_records_for_document(self, document_id: str) -> None:
        """Delete query history whose retrieved chunk IDs belong to one document."""
        result = await self.db.execute(
            select(RagChunk.id).where(RagChunk.document_id == document_id)
        )
        chunk_ids = list(result.scalars().all())
        for start in range(0, len(chunk_ids), 100):
            batch = chunk_ids[start : start + 100]
            await self.db.execute(
                delete(RagQueryRecord).where(
                    or_(
                        *[
                            RagQueryRecord.retrieved_chunk_ids_json.like(f'%"{chunk_id}"%')
                            for chunk_id in batch
                        ]
                    )
                )
            )

    async def delete_ingestion_jobs_for_document(self, document_id: str) -> None:
        await self.db.execute(
            delete(RagIngestionJob).where(RagIngestionJob.document_id == document_id)
        )

    async def scrub_deleted_document(self, document_id: str) -> None:
        result = await self.db.execute(select(RagDocument).where(RagDocument.id == document_id))
        document = result.scalar_one_or_none()
        if document is None or document.deleted_at is None:
            return
        document.filename = "deleted-document"
        document.original_filename = "deleted-document"
        document.content_fingerprint = None
        document.storage_path = None
        document.metadata_json = "{}"
        document.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def list_chunks_for_documents(self, document_ids: list[str]) -> list[RagChunk]:
        if not document_ids:
            return []
        result = await self.db.execute(
            select(RagChunk)
            .where(RagChunk.document_id.in_(document_ids))
            .order_by(RagChunk.document_id, RagChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def list_chunks_for_user_by_ids(
        self, user_id: str, chunk_ids: list[str]
    ) -> list[RagChunk]:
        if not chunk_ids:
            return []
        result = await self.db.execute(
            select(RagChunk).where(
                RagChunk.user_id == user_id,
                RagChunk.id.in_(chunk_ids),
            )
        )
        return list(result.scalars().all())

    async def list_chunks_for_document(
        self,
        document_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[RagChunk], int]:
        stmt = (
            select(RagChunk)
            .where(RagChunk.document_id == document_id)
            .order_by(RagChunk.chunk_index)
        )
        return await paginate_scalars(self.db, stmt, limit=limit, offset=offset)

    async def list_chunks_for_document_cursor(
        self, document_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[RagChunk], str | None, bool]:
        stmt = select(RagChunk).where(RagChunk.document_id == document_id)
        return await paginate_cursor_scalars(
            self.db,
            stmt,
            limit=limit,
            cursor=cursor,
            sort_column=RagChunk.created_at,
            id_column=RagChunk.id,
        )

    async def pgvector_is_available(self) -> bool:
        return (await pgvector_readiness(self.db)).available

    async def similarity_search_indexed(
        self,
        *,
        user_id: str,
        project_id: str | None,
        document_ids: list[str] | None,
        source_type: str | None,
        query: str,
        query_embedding: list[float],
        top_k: int,
        score_threshold: float,
        candidate_limit: int | None = None,
        organization_id: str | None = None,
    ) -> list[RetrievedChunk]:
        readiness = await pgvector_readiness(self.db)
        if not readiness.available:
            raise PgVectorUnavailableError(readiness.reason or "readiness_check_failed")
        if not embedding_is_indexable(query_embedding):
            raise PgVectorUnavailableError("query_dimension_mismatch")

        filters = [
            (
                "(c.user_id = :user_id OR c.organization_id = :organization_id)"
                if organization_id is not None
                else "c.user_id = :user_id"
            ),
            "c.embedding IS NOT NULL",
            "d.status = 'indexed'",
            "d.deleted_at IS NULL",
            "(1 - (c.embedding <=> CAST(:query_vec AS vector))) >= :score_threshold",
        ]
        params: dict = {
            "user_id": user_id,
            "query_vec": vector_literal(query_embedding),
            "score_threshold": score_threshold,
            "candidate_limit": max(top_k, candidate_limit or top_k),
            "search_query": query,
        }
        if organization_id is not None:
            params["organization_id"] = organization_id
        if project_id:
            filters.append("c.project_id = :project_id")
            params["project_id"] = project_id
        if organization_id is not None:
            filters.append("c.organization_id = :organization_id")
            params["organization_id"] = organization_id
        if document_ids:
            filters.append("c.document_id = ANY(:document_ids)")
            params["document_ids"] = document_ids
        if source_type:
            filters.append("d.source_type = :source_type")
            params["source_type"] = source_type

        sql = f"""
            SELECT
                c.id AS chunk_id,
                c.document_id,
                c.content,
                c.chunk_index,
                c.metadata_json,
                d.original_filename,
                (1 - (c.embedding <=> CAST(:query_vec AS vector))) AS score,
                ts_rank_cd(
                    to_tsvector('simple', coalesce(c.content, '')),
                    plainto_tsquery('simple', :search_query)
                ) AS lexical_score
            FROM rag_chunks c
            INNER JOIN rag_documents d ON d.id = c.document_id
            WHERE {" AND ".join(filters)}
            ORDER BY c.embedding <=> CAST(:query_vec AS vector)
            LIMIT :candidate_limit
        """
        try:
            result = await self.db.execute(text(sql), params)
        except Exception as exc:
            logger.exception("Indexed pgvector search failed")
            reset_pgvector_readiness_cache()
            raise PgVectorUnavailableError("query_failed") from exc

        rows = result.mappings().all()
        retrieved: list[RetrievedChunk] = []
        for row in rows:
            meta = json.loads(row["metadata_json"] or "{}")
            retrieved.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    content=row["content"],
                    score=round(float(row["score"]), 4),
                    filename=row["original_filename"],
                    chunk_index=row["chunk_index"],
                    page_number=meta.get("page_number"),
                    metadata={**meta, "lexical_score": float(row["lexical_score"] or 0.0)},
                )
            )
        return retrieved

    async def create_ingestion_job(
        self, *, document_id: str, user_id: str, project_id: str | None
    ) -> RagIngestionJob:
        job = RagIngestionJob(
            document_id=document_id,
            user_id=user_id,
            project_id=project_id,
            status=IngestionJobStatus.PENDING.value,
            deadline_at=datetime.now(UTC)
            + timedelta(seconds=settings.RAG_INGESTION_JOB_TIMEOUT_SECONDS),
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_latest_ingestion_job_for_document(
        self, document_id: str
    ) -> RagIngestionJob | None:
        result = await self.db.execute(
            select(RagIngestionJob)
            .where(RagIngestionJob.document_id == document_id)
            .order_by(RagIngestionJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_ingestion_job_for_document(
        self, document_id: str, *, now: datetime | None = None
    ) -> RagIngestionJob | None:
        current_time = now or datetime.now(UTC)
        result = await self.db.execute(
            select(RagIngestionJob)
            .where(
                RagIngestionJob.document_id == document_id,
                RagIngestionJob.status.in_(
                    [IngestionJobStatus.PENDING.value, IngestionJobStatus.RUNNING.value]
                ),
                or_(
                    RagIngestionJob.deadline_at.is_(None),
                    RagIngestionJob.deadline_at > current_time,
                ),
            )
            .order_by(RagIngestionJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_ingestion_job(
        self, job_id: str, *, for_update: bool = False
    ) -> RagIngestionJob | None:
        query = select(RagIngestionJob).where(RagIngestionJob.id == job_id)
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_ingestion_jobs_for_user(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[RagIngestionJob], int]:
        stmt = (
            select(RagIngestionJob)
            .where(RagIngestionJob.user_id == user_id)
            .order_by(RagIngestionJob.created_at.desc())
        )
        return await paginate_scalars(self.db, stmt, limit=limit, offset=offset)

    async def update_ingestion_job(
        self,
        job: RagIngestionJob,
        *,
        status: IngestionJobStatus,
        error_message: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> RagIngestionJob:
        job.status = status.value
        if error_message is not None:
            job.error_message = error_message
        if started:
            job.started_at = datetime.now(UTC)
            job.attempts = int(getattr(job, "attempts", 0) or 0) + 1
        job.heartbeat_at = datetime.now(UTC)
        if finished:
            job.finished_at = datetime.now(UTC)
        await self.db.flush()
        return job

    async def touch_ingestion_job(self, job: RagIngestionJob) -> None:
        job.heartbeat_at = datetime.now(UTC)
        await self.db.flush()

    async def create_query_record(
        self,
        *,
        user_id: str,
        project_id: str | None,
        organization_id: str | None,
        query: str,
        answer: str,
        retrieved_chunk_ids: list[str],
        model_name: str,
        latency_ms: int,
    ) -> RagQueryRecord:
        row = RagQueryRecord(
            user_id=user_id,
            project_id=project_id,
            organization_id=organization_id,
            query=query,
            answer=answer,
            retrieved_chunk_ids_json=json.dumps(retrieved_chunk_ids, ensure_ascii=True),
            model_name=model_name,
            latency_ms=latency_ms,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_queries_for_user(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[RagQueryRecord], int]:
        stmt = (
            select(RagQueryRecord)
            .where(RagQueryRecord.user_id == user_id)
            .order_by(RagQueryRecord.created_at.desc())
        )
        return await paginate_scalars(self.db, stmt, limit=limit, offset=offset)

    async def list_queries_for_user_cursor(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[RagQueryRecord], str | None, bool]:
        stmt = select(RagQueryRecord).where(RagQueryRecord.user_id == user_id)
        return await paginate_cursor_scalars(
            self.db,
            stmt,
            limit=limit,
            cursor=cursor,
            sort_column=RagQueryRecord.created_at,
            id_column=RagQueryRecord.id,
        )
