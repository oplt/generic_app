from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface, NavEntry

MANIFEST = ModuleManifest(
    key="chat",
    version="1.0.0",
    label="Knowledge chat",
    description="Document-grounded chat over the RAG corpus.",
    always_enabled=False,
    optional=False,
    surface=ModuleSurface.USER_FACING,
    dependencies=("rag", "ai", "identity_access"),
    backend_router_keys=("chat",),
    celery_queues=(),
    scheduled_tasks=("cleanup-expired-chat-conversations",),
    required_permissions=("rag.read",),
    nav_entries=(
        NavEntry(
            label="Knowledge chat",
            path="/knowledge-chat",
            group="workspace",
            icon="knowledge",
            required_permission="rag.read",
        ),
    ),
    frontend_routes=(
        FrontendRoute(
            path="/knowledge-chat",
            page_key="chat.knowledge",
            required_permission="rag.read",
        ),
    ),
)
