from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.core.config import settings
from backend.lib.project_access import ProjectAccessPort, SqlAlchemyProjectAccessPort
from backend.lib.retrieval_cache import invalidate_retrieval_cache_for_document
from backend.modules.rag.application.chunking_service import ChunkingService
from backend.modules.rag.application.document_identity import content_fingerprint, display_filename
from backend.modules.rag.application.document_parser_service import DocumentParserService
from backend.modules.rag.application.embedding_service import EmbeddingService
from backend.modules.rag.application.malware_scanner import (
    MalwareScanError,
    build_malware_scanner,
)
from backend.modules.rag.application.rag_policy_service import RagPolicyService
from backend.modules.rag.domain.enums import DocumentStatus, IngestionJobStatus
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.file_storage_adapter import FileStorageAdapter
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from backend.modules.rag.infrastructure.vector_store_adapter import build_vector_store
from backend.modules.rag.workers import queue_document_cleanup, queue_document_indexing
from backend.workers.outbox import enqueue_job_event
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentUploadResult:
    document: object
    job: object
    duplicate: bool = False

    def __iter__(self):
        # Preserve the historical ``document, job = ...`` service contract.
        yield self.document
        yield self.job


class DocumentIngestionService:
    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()
        self.repo = RagRepository(db)
        self.project_access: ProjectAccessPort = SqlAlchemyProjectAccessPort(db)
        self.parser = DocumentParserService()
        self.chunker = ChunkingService(self.config)
        self.embeddings = EmbeddingService(self.config)
        self.policy = RagPolicyService()
        self.storage = FileStorageAdapter()
        self.vector_store = build_vector_store(db, self.config)
        self.malware_scanner = build_malware_scanner()

    async def upload_document(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        project_id: str | None = None,
        organization_id: str | None = None,
        metadata: dict | None = None,
    ):
        if not self.config.enabled:
            raise HTTPException(status_code=503, detail="RAG is disabled")

        if len(content) > self.config.max_file_bytes:
            raise HTTPException(status_code=413, detail="File too large")

        safe_filename = display_filename(filename)
        fingerprint = content_fingerprint(content)
        if not self.policy.is_allowed_file_type(safe_filename, self.config.allowed_file_types):
            raise HTTPException(status_code=400, detail="Unsupported file type")
        detected_content_type = self.policy.detect_content_type(safe_filename, content)
        if detected_content_type is None:
            raise HTTPException(status_code=400, detail="File content does not match its extension")

        await self._scan_or_reject(
            filename=safe_filename,
            content_type=detected_content_type,
            content=content,
        )

        scope_result = self.project_access.resolve_ownership_scope(user_id, project_id)
        if inspect.isawaitable(scope_result):
            scope = await scope_result
            project_id = scope.project_id
            organization_id = scope.organization_id
        else:
            # Compatibility for narrow legacy test doubles and ports.
            if project_id:
                await self._ensure_project_access(user_id, project_id)

        duplicate = await self._find_duplicate(
            user_id=user_id,
            project_id=project_id,
            fingerprint=fingerprint,
            organization_id=organization_id,
        )
        if duplicate is not None:
            document, job = duplicate
            return DocumentUploadResult(document=document, job=job, duplicate=True)

        storage_path = await self.storage.store_document(
            user_id=user_id,
            filename=safe_filename,
            content=content,
            content_type=detected_content_type,
        )

        document = await self.repo.create_document(
            user_id=user_id,
            filename=safe_filename,
            original_filename=safe_filename,
            content_type=detected_content_type,
            content_fingerprint=fingerprint,
            storage_path=storage_path,
            project_id=project_id,
            organization_id=organization_id,
            source_type="upload",
            metadata={
                "size_bytes": len(content),
                "content_fingerprint": fingerprint,
                **self._embedding_metadata(),
                **(metadata or {}),
            },
        )
        job = await self.repo.create_ingestion_job(
            document_id=document.id,
            user_id=user_id,
            project_id=project_id,
        )
        await enqueue_job_event(
            self.db,
            job_id=job.id,
            job_type="rag-indexing",
            payload={"document_id": document.id, "user_id": user_id, "job_id": job.id},
        )
        await self.db.commit()
        await self.db.refresh(document)
        await self.db.refresh(job)
        metrics.rag_document_upload_total.inc()
        if settings.CELERY_TASK_ALWAYS_EAGER:
            queue_document_indexing(
                document_id=document.id,
                user_id=user_id,
                job_id=job.id,
            )

        return DocumentUploadResult(document=document, job=job)

    async def enqueue_document_indexing(
        self,
        *,
        document_id: str,
        user_id: str,
        file_content: bytes | None = None,
        is_admin: bool = False,
        force_new_attempt: bool = False,
    ):
        document = await self._get_document_for_indexing(
            document_id=document_id,
            user_id=user_id,
            is_admin=is_admin,
        )
        if not force_new_attempt:
            active_job = await self._get_active_job(document.id)
            if active_job is not None:
                return active_job
        job = await self.repo.create_ingestion_job(
            document_id=document.id,
            user_id=user_id,
            project_id=document.project_id,
        )
        await enqueue_job_event(
            self.db,
            job_id=job.id,
            job_type="rag-indexing",
            payload={"document_id": document.id, "user_id": user_id, "job_id": job.id},
        )
        await self.db.commit()
        await self.db.refresh(job)
        if settings.CELERY_TASK_ALWAYS_EAGER:
            queue_document_indexing(document_id=document.id, user_id=user_id, job_id=job.id)
        return job

    async def index_document(
        self,
        *,
        document_id: str,
        user_id: str,
        file_content: bytes | None = None,
        is_admin: bool = False,
        job_id: str | None = None,
    ):
        document = await self._get_document_for_indexing(
            document_id=document_id,
            user_id=user_id,
            is_admin=is_admin,
        )
        if job_id:
            job = await self.repo.get_ingestion_job(job_id, for_update=True)
            if not job or job.document_id != document.id:
                raise HTTPException(status_code=404, detail="Ingestion job not found")
            if job.status == IngestionJobStatus.COMPLETED.value:
                return document, [], job
            if (
                job.status == IngestionJobStatus.RUNNING.value
                and job.heartbeat_at is not None
                and datetime.now(UTC) - job.heartbeat_at < timedelta(minutes=10)
            ):
                logger.info("Skipping duplicate active indexing job=%s", job.id)
                return document, [], job
        else:
            job = await self.repo.create_ingestion_job(
                document_id=document.id,
                user_id=user_id,
                project_id=document.project_id,
            )
        now = datetime.now(UTC)
        deadline_at = getattr(job, "deadline_at", None)
        if isinstance(deadline_at, datetime) and deadline_at <= now:
            await self.repo.update_ingestion_job(
                job,
                status=IngestionJobStatus.FAILED,
                error_message="Ingestion job deadline exceeded",
                finished=True,
            )
            await self.db.commit()
            raise HTTPException(status_code=409, detail="Ingestion job deadline exceeded")
        attempts = getattr(job, "attempts", 0)
        attempts = attempts if isinstance(attempts, int) else 0
        if attempts >= settings.RAG_INGESTION_MAX_ATTEMPTS:
            await self.repo.update_ingestion_job(
                job,
                status=IngestionJobStatus.FAILED,
                error_message="Ingestion job retry limit exceeded",
                finished=True,
            )
            await self.db.commit()
            raise HTTPException(status_code=409, detail="Ingestion job retry limit exceeded")
        await self.repo.update_ingestion_job(job, status=IngestionJobStatus.RUNNING, started=True)
        await self.repo.update_document_status(document, DocumentStatus.VALIDATING)
        await self.db.commit()

        try:
            content = file_content
            if content is None and document.storage_path:
                content = await self.storage.download_document(document.storage_path)
            if content is None:
                raise HTTPException(
                    status_code=422,
                    detail="No file content available for indexing",
                )

            await self._scan_or_reject(
                filename=document.original_filename,
                content_type=document.content_type,
                content=content,
            )

            await self._touch_job(job)
            await self.repo.update_document_status(document, DocumentStatus.EXTRACTING)
            await self.db.commit()
            try:
                parser_timeout = getattr(
                    self.config, "parser_timeout_seconds", settings.RAG_PARSER_TIMEOUT_SECONDS
                )
                if not isinstance(parser_timeout, (int, float)):
                    parser_timeout = settings.RAG_PARSER_TIMEOUT_SECONDS
                parsed = await asyncio.wait_for(
                    self.parser.parse_bytes(
                        content=content,
                        filename=document.original_filename,
                        content_type=document.content_type,
                        metadata={"document_id": document.id},
                    ),
                    timeout=parser_timeout,
                )
            except TimeoutError as exc:
                raise HTTPException(status_code=504, detail="Document parser timed out") from exc
            if not parsed:
                raise ValueError("No text extracted from document")
            metrics.rag_parse_success_total.inc()
            await self._touch_job(job)

            await self.repo.update_document_status(document, DocumentStatus.CHUNKING)
            await self.db.commit()

            chunks = await self.chunker.chunk(
                parsed,
                document_id=document.id,
                user_id=document.user_id,
                filename=document.original_filename,
                project_id=document.project_id,
                organization_id=document.organization_id,
            )
            injection_flags = 0
            for chunk in chunks:
                injection_match = self.policy.find_prompt_injection(chunk.content)
                if injection_match:
                    chunk.metadata = {
                        **chunk.metadata,
                        "prompt_injection_suspected": True,
                        "prompt_injection_reason": injection_match,
                    }
                    injection_flags += 1
            if injection_flags:
                logger.warning(
                    "Suspected prompt injection in %s chunk(s) for document=%s user=%s",
                    injection_flags,
                    document.id,
                    document.user_id,
                )
            embedding_metadata = self._embedding_metadata()
            for chunk in chunks:
                chunk.metadata.update(embedding_metadata)
            metrics.rag_chunk_count.observe(len(chunks))

            await self.repo.update_document_status(document, DocumentStatus.EMBEDDING)
            await self.db.commit()

            texts = [chunk.content for chunk in chunks]
            vectors = await self.embeddings.embed_texts(texts)
            await self._touch_job(job)
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk.embedding = vector

            chunk_rows = await self.repo.replace_chunks(
                document,
                [
                    {
                        "chunk_index": c.chunk_index,
                        "content": c.content,
                        "token_count": c.token_count,
                        "metadata": c.metadata,
                        "embedding": c.embedding or [],
                        "vector_external_id": c.id,
                    }
                    for c in chunks
                ],
            )

            await self.repo.update_document_status(document, DocumentStatus.INDEXED)
            metadata = json.loads(document.metadata_json or "{}")
            metadata["chunk_count"] = len(chunk_rows)
            metadata.update(self._embedding_metadata())
            document.metadata_json = json.dumps(metadata, ensure_ascii=True)
            await self.repo.update_ingestion_job(
                job, status=IngestionJobStatus.COMPLETED, finished=True
            )
            document.updated_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(document)
            await invalidate_retrieval_cache_for_document(
                user_id=document.user_id,
                project_id=document.project_id,
                organization_id=document.organization_id,
            )
            return document, chunk_rows, job
        except HTTPException as exc:
            await self.repo.update_document_status(document, DocumentStatus.FAILED)
            await self.repo.update_ingestion_job(
                job,
                status=IngestionJobStatus.FAILED,
                error_message=self._safe_ingestion_error(exc),
                finished=True,
            )
            await self.db.commit()
            raise
        except Exception as exc:
            logger.error(
                "Document indexing failed document=%s error_type=%s",
                document_id,
                type(exc).__name__,
            )
            metrics.rag_parse_failure_total.inc()
            metrics.rag_vector_upsert_failure_total.inc()
            await self.repo.update_document_status(document, DocumentStatus.FAILED)
            await self.repo.update_ingestion_job(
                job,
                status=IngestionJobStatus.FAILED,
                error_message="Document indexing failed",
                finished=True,
            )
            await self.db.commit()
            raise HTTPException(status_code=502, detail="Document indexing failed") from exc

    async def delete_document(self, *, document_id: str, user_id: str, is_admin: bool = False):
        document = await self.repo.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        if document.user_id != user_id and not is_admin:
            metrics.rag_permission_denied_total.inc()
            raise HTTPException(status_code=403, detail="You cannot delete this document")

        from backend.modules.chat.repository import ChatRepository

        await self.repo.soft_delete_document(document)
        await self.repo.delete_query_records_for_document(document_id)
        await self.repo.delete_ingestion_jobs_for_document(document_id)
        await ChatRepository(self.db).delete_sources_for_document(document_id)
        await self.db.commit()
        await invalidate_retrieval_cache_for_document(
            user_id=document.user_id,
            project_id=document.project_id,
            organization_id=document.organization_id,
        )
        queue_document_cleanup(
            document_id=document_id,
            user_id=document.user_id,
            storage_path=document.storage_path,
        )

    async def cleanup_deleted_document(
        self,
        *,
        document_id: str,
        user_id: str,
        storage_path: str | None,
    ) -> None:
        # Cleanup runs after the document is hidden. Keep all derived DB data in
        # one transaction so retries cannot leave stale citations behind.
        from backend.modules.chat.repository import ChatRepository

        await self.repo.delete_query_records_for_document(document_id)
        await ChatRepository(self.db).delete_sources_for_document(document_id)
        await self.vector_store.delete_document(document_id, user_id)
        await self.storage.delete_document(storage_path)
        await self.repo.delete_ingestion_jobs_for_document(document_id)
        await self.repo.scrub_deleted_document(document_id)
        await self.db.commit()
        logger.info("RAG document cleanup completed document=%s user=%s", document_id, user_id)

    async def _get_document_for_indexing(
        self,
        *,
        document_id: str,
        user_id: str,
        is_admin: bool,
    ):
        document = await self.repo.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        if document.user_id != user_id and not is_admin:
            raise HTTPException(status_code=403, detail="You cannot index this document")
        if document.project_id:
            await self._ensure_project_access(user_id, document.project_id)
        return document

    async def _ensure_project_access(self, user_id: str, project_id: str) -> None:
        await self.project_access.ensure_project_access(user_id, project_id)

    async def _scan_or_reject(self, *, filename: str, content_type: str, content: bytes) -> None:
        if not settings.RAG_MALWARE_SCAN_ENABLED:
            if settings.is_production:
                metrics.rag_malware_scan_failure_total.inc()
                raise HTTPException(
                    status_code=503,
                    detail="Malware scanning is required for production uploads",
                )
            return
        try:
            result = await self.malware_scanner.scan(
                filename=filename,
                content_type=content_type,
                content=content,
            )
        except MalwareScanError as exc:
            metrics.rag_malware_scan_failure_total.inc()
            raise HTTPException(status_code=503, detail="Malware scan unavailable") from exc
        metrics.rag_malware_scan_total.inc()
        if not result.clean:
            metrics.rag_malware_rejected_total.inc()
            raise HTTPException(status_code=422, detail="Uploaded file failed malware scanning")

    async def _touch_job(self, job) -> None:
        deadline_at = getattr(job, "deadline_at", None)
        if isinstance(deadline_at, datetime) and deadline_at <= datetime.now(UTC):
            raise RuntimeError("Ingestion job deadline exceeded")
        result = self.repo.touch_ingestion_job(job)
        if inspect.isawaitable(result):
            await result

    @staticmethod
    def _safe_ingestion_error(exc: HTTPException) -> str:
        return {
            413: "Uploaded file is too large",
            422: "Uploaded document failed validation",
            502: "Document indexing failed",
            503: "Required document security service unavailable",
            504: "Document parser timed out",
        }.get(exc.status_code, "Document indexing failed")

    async def _find_duplicate(
        self,
        *,
        user_id: str,
        project_id: str | None,
        fingerprint: str,
        organization_id: str | None = None,
    ) -> tuple[object, object] | None:
        if not isinstance(self.repo, RagRepository):
            return None
        document = await self.repo.find_document_by_fingerprint(
            user_id=user_id,
            project_id=project_id,
            fingerprint=fingerprint,
            organization_id=organization_id,
        )
        if document is None:
            return None
        job = await self.repo.get_latest_ingestion_job_for_document(document.id)
        if job is None:
            job = await self.repo.create_ingestion_job(
                document_id=document.id,
                user_id=user_id,
                project_id=project_id,
            )
            await self.db.commit()
        return document, job

    async def _get_active_job(self, document_id: str):
        if not isinstance(self.repo, RagRepository):
            return None
        return await self.repo.get_active_ingestion_job_for_document(document_id)

    def _embedding_metadata(self) -> dict[str, object]:
        values = {
            "embedding_provider": getattr(self.config, "embedding_provider", None),
            "embedding_model": getattr(self.config, "embedding_model", None),
            "embedding_dimensions": getattr(self.config, "embedding_dimensions", None),
        }
        return {
            key: value
            for key, value in values.items()
            if isinstance(value, (str, int, float)) and not isinstance(value, bool)
        }
