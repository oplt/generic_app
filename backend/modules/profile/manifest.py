from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface, NavEntry

MANIFEST = ModuleManifest(
    key="profile",
    version="1.0.0",
    label="Profiles",
    description="User profile and preference management.",
    always_enabled=True,
    surface=ModuleSurface.USER_FACING,
    dependencies=("identity_access", "users"),
    backend_router_keys=("profile",),
    nav_entries=(
        NavEntry(label="Settings", path="/profile", group="workspace", icon="settings"),
    ),
    frontend_routes=(FrontendRoute(path="/profile", page_key="profile.settings"),),
)
