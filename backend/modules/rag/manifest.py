from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="rag",
    version="1.0.0",
    label="RAG",
    description="Document ingestion, retrieval, and knowledge grounding.",
    always_enabled=False,
    optional=False,
    surface=ModuleSurface.ADMIN_FACING,
    dependencies=("ai", "storage", "projects"),
    backend_router_keys=("rag",),
    celery_queues=("ingestion", "cleanup"),
    required_permissions=("rag.read", "rag.manage"),
    settings_prefixes=("RAG_",),
    health_checks=("vector", "storage"),
    database_requirements=(
        "rag_documents",
        "rag_chunks",
        "rag_ingestion_jobs",
        "rag_index_versions",
    ),
    frontend_routes=(
        FrontendRoute(path="/admin/rag-indexes", page_key="rag.admin.indexes"),
        FrontendRoute(path="/admin/rag/evaluation", page_key="rag.admin.evaluation"),
    ),
)
