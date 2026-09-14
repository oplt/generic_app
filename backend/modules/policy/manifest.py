from backend.modules.manifests.types import ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="policy",
    version="1.0.0",
    label="Policy / RBAC",
    description=(
        "Capability permissions, roles, and assignments. "
        "Surfaced under Admin Users (Access tab + role dialogs); "
        "frontend feature folder: admin-users."
    ),
    always_enabled=True,
    user_visible=False,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="admin.users",
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
