from backend.modules.manifests.types import ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="users",
    version="1.0.0",
    label="Users",
    description=(
        "User directory and self-service account APIs. "
        "Admin directory UI: features/admin-users (embedding_host admin.users); "
        "self-service account UI: Profile / Settings tabs."
    ),
    always_enabled=True,
    user_visible=False,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="admin.users",
    dependencies=("identity_access",),
    backend_router_keys=("users",),
    database_requirements=("users",),
)
