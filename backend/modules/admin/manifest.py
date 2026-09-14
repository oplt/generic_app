from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="admin",
    version="1.0.0",
    label="Admin",
    description="Administrative user and audit surfaces.",
    always_enabled=True,
    dependencies=("identity_access", "policy"),
    backend_router_keys=("admin",),
    required_permissions=("admin.manage", "users.manage"),
)
