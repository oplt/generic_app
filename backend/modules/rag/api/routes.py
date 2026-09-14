"""RAG HTTP routes composed from document, query, job, and admin resources."""

from backend.modules.rag.api.admin_routes import router as admin_router
from backend.modules.rag.api.document_routes import list_document_chunks
from backend.modules.rag.api.document_routes import router as document_router
from backend.modules.rag.api.evaluation_routes import router as evaluation_router
from backend.modules.rag.api.job_routes import router as job_router
from backend.modules.rag.api.query_routes import router as query_router
from backend.modules.rag.workers import (
    queue_document_indexing,  # noqa: F401 — compatibility patch target
)
from fastapi import APIRouter

router = APIRouter()
router.include_router(document_router)
router.include_router(query_router)
router.include_router(job_router)
router.include_router(admin_router)
router.include_router(evaluation_router)

__all__ = ["list_document_chunks", "queue_document_indexing", "router"]
