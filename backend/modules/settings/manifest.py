from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="settings",
    version="1.0.0",
    label="Settings",
    description="Application and platform configuration settings.",
    always_enabled=True,
    backend_router_keys=("settings",),
    settings_prefixes=("platform.",),
    database_requirements=("settings",),
)
