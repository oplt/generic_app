from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="admin",
    version="1.0.0",
    label="Admin",
    description=(
        "Administrative user directory and access-control host. "
        "Frontend feature folder: admin-users (page_key admin.users)."
    ),
    always_enabled=True,
    surface=ModuleSurface.ADMIN_FACING,
    dependencies=("identity_access", "policy", "audit"),
    backend_router_keys=("admin",),
    required_permissions=("admin.manage", "users.manage"),
    frontend_routes=(
        FrontendRoute(path="/admin/users", page_key="admin.users"),
    ),
)
