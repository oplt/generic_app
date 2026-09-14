from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="memory",
    version="1.0.0",
    label="Memory",
    description="Long-term conversational memory extraction and recall.",
    always_enabled=False,
    optional=False,
    dependencies=("identity_access", "ai"),
    backend_router_keys=("memory",),
    celery_queues=("memory",),
    database_requirements=("memory_registry",),
)
