from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="inventory",
    version="1.0.0",
    label="Inventory",
    description="Inventory module scaffolded by generic-app create-module.",
    always_enabled=False,
    optional=True,
    dependencies=('identity_access',),
    backend_router_keys=("inventory",),
)
