from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="settings",
    version="1.0.0",
    label="Settings",
    description=(
        "Application configuration settings. "
        "Frontend feature folder: settings-admin (page_key settings.admin)."
    ),
    always_enabled=True,
    surface=ModuleSurface.ADMIN_FACING,
    backend_router_keys=("settings",),
    settings_prefixes=("platform.",),
    database_requirements=("settings",),
    frontend_routes=(
        FrontendRoute(path="/admin/settings", page_key="settings.admin"),
    ),
)
