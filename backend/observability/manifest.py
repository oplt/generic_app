from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="observability",
    version="1.0.0",
    label="Observability",
    description="Health, metrics links, and diagnostics surfaces.",
    always_enabled=True,
    backend_router_keys=("observability",),
    required_permissions=("diagnostics.read",),
    health_checks=("database", "redis", "queue", "storage"),
)
