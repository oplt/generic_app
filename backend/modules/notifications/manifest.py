from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="notifications",
    version="1.0.0",
    label="Notifications",
    description="In-app notification delivery and preferences.",
    always_enabled=True,
    dependencies=("identity_access",),
    backend_router_keys=("notifications",),
    database_requirements=("notifications",),
)
