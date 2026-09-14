from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="notifications",
    version="1.0.0",
    label="Notifications",
    description="In-app notification delivery and preferences.",
    always_enabled=True,
    surface=ModuleSurface.USER_FACING,
    dependencies=("identity_access",),
    backend_router_keys=("notifications",),
    database_requirements=("notifications",),
    frontend_routes=(
        FrontendRoute(path="/notifications", page_key="notifications.inbox"),
    ),
)
