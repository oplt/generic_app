from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="observability",
    version="1.0.0",
    label="Observability",
    description="Health, metrics links, and diagnostics surfaces.",
    always_enabled=True,
    surface=ModuleSurface.USER_FACING,
    backend_router_keys=("observability",),
    required_permissions=("diagnostics.read",),
    health_checks=("database", "redis", "queue"),
    frontend_routes=(
        FrontendRoute(path="/observability", page_key="observability.main"),
    ),
)
