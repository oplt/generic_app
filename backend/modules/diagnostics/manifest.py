from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="diagnostics",
    version="1.0.0",
    label="Diagnostics",
    description="Production-safe application and infrastructure diagnostics.",
    always_enabled=True,
    dependencies=("policy", "observability"),
    backend_router_keys=("diagnostics",),
    required_permissions=("diagnostics.read",),
    health_checks=("database", "redis", "queue", "storage", "vector"),
)
