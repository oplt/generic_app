from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="diagnostics",
    version="1.0.0",
    label="Diagnostics",
    description="Production-safe application and infrastructure diagnostics.",
    always_enabled=False,
    optional=False,
    surface=ModuleSurface.ADMIN_FACING,
    dependencies=("policy", "observability"),
    backend_router_keys=("diagnostics",),
    required_permissions=("diagnostics.read",),
    # Probe UI only — readiness requirements come from capability modules (rag/…).
    health_checks=(),
    frontend_routes=(
        FrontendRoute(path="/admin/diagnostics", page_key="diagnostics.admin"),
    ),
)
