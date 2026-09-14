from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="rag",
    version="1.0.0",
    label="RAG",
    description="Document ingestion, retrieval, and knowledge grounding.",
    always_enabled=True,
    dependencies=("ai", "storage", "projects"),
    backend_router_keys=("rag",),
    celery_queues=("ingestion", "cleanup"),
    required_permissions=("rag.read", "rag.manage"),
    settings_prefixes=("RAG_",),
    health_checks=("vector", "storage"),
    database_requirements=("rag_documents", "rag_chunks", "rag_ingestion_jobs", "rag_index_versions"),
)
