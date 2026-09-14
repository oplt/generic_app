from backend.modules.manifests.types import FrontendRoute, ModuleManifest

MANIFEST = ModuleManifest(
    key="diagnostics",
    version="1.0.0",
    label="Diagnostics",
    description="Production-safe application and infrastructure diagnostics.",
    always_enabled=False,
    optional=False,
    dependencies=("policy", "observability"),
    backend_router_keys=("diagnostics",),
    required_permissions=("diagnostics.read",),
    health_checks=("database", "redis", "queue", "storage", "vector"),
    frontend_routes=(
        FrontendRoute(path="/admin/diagnostics", page_key="diagnostics.admin"),
    ),
)
