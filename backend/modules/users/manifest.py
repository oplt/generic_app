from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="users",
    version="1.0.0",
    label="Users",
    description="User directory and account surfaces.",
    always_enabled=True,
    dependencies=("identity_access",),
    backend_router_keys=("users",),
    database_requirements=("users",),
)
