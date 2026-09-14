from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="policy",
    version="1.0.0",
    label="Policy / RBAC",
    description="Capability permissions, roles, and assignments.",
    always_enabled=True,
    dependencies=("identity_access",),
    backend_router_keys=("policy",),
    required_permissions=("admin.manage",),
    database_requirements=(
        "policy_permissions",
        "policy_roles",
        "policy_role_permissions",
        "policy_role_assignments",
    ),
)
