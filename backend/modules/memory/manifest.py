from backend.modules.manifests.types import ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="memory",
    version="1.0.0",
    label="Memory",
    description=(
        "Long-term conversational memory extraction and recall. "
        "End-user list/delete controls live on Profile (no vector internals); "
        "search/write/audit remain agent/API use."
    ),
    always_enabled=False,
    optional=False,
    user_visible=False,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="profile.settings",
    dependencies=("identity_access", "ai"),
    backend_router_keys=("memory",),
    celery_queues=("memory",),
    database_requirements=("memory_registry",),
)
