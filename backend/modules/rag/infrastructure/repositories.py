from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from backend.modules.rag.domain.enums import DocumentStatus, IngestionJobStatus
from backend.modules.rag.infrastructure.models import (
    RagChunk,
    RagDocument,
    RagIngestionJob,
    RagQueryRecord,
)
from sqlalchemy import delete, select
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
    ) -> list[RagDocument]:
        stmt = select(RagDocument).where(
            RagDocument.user_id == user_id,
            RagDocument.deleted_at.is_(None),
        )
        if project_id:
            stmt = stmt.where(RagDocument.project_id == project_id)
        stmt = stmt.order_by(RagDocument.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_indexed_documents(
        self,
        user_id: str,
        *,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
    ) -> list[RagDocument]:
        stmt = select(RagDocument).where(
            RagDocument.user_id == user_id,
            RagDocument.status == DocumentStatus.INDEXED.value,
            RagDocument.deleted_at.is_(None),
        )
        if project_id:
            stmt = stmt.where(RagDocument.project_id == project_id)
        if document_ids:
            stmt = stmt.where(RagDocument.id.in_(document_ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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
                embedding_json=json.dumps(item.get("embedding", []), ensure_ascii=True),
                vector_external_id=item.get("vector_external_id"),
            )
            self.db.add(row)
            rows.append(row)
        await self.db.flush()
        return rows

    async def list_chunks_for_documents(self, document_ids: list[str]) -> list[RagChunk]:
        if not document_ids:
            return []
        result = await self.db.execute(
            select(RagChunk)
            .where(RagChunk.document_id.in_(document_ids))
            .order_by(RagChunk.document_id, RagChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def list_chunks_for_document(self, document_id: str) -> list[RagChunk]:
        result = await self.db.execute(
            select(RagChunk)
            .where(RagChunk.document_id == document_id)
            .order_by(RagChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def create_ingestion_job(
        self, *, document_id: str, user_id: str, project_id: str | None
    ) -> RagIngestionJob:
        job = RagIngestionJob(
            document_id=document_id,
            user_id=user_id,
            project_id=project_id,
            status=IngestionJobStatus.PENDING.value,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_ingestion_job(self, job_id: str) -> RagIngestionJob | None:
        result = await self.db.execute(
            select(RagIngestionJob).where(RagIngestionJob.id == job_id)
        )
        return result.scalar_one_or_none()

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
        if finished:
            job.finished_at = datetime.now(UTC)
        await self.db.flush()
        return job

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

    async def list_queries_for_user(self, user_id: str, *, limit: int = 50) -> list[RagQueryRecord]:
        result = await self.db.execute(
            select(RagQueryRecord)
            .where(RagQueryRecord.user_id == user_id)
            .order_by(RagQueryRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
