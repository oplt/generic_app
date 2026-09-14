from backend.modules.manifests.types import FrontendRoute, ModuleManifest, NavEntry

MANIFEST = ModuleManifest(
    key="calendar",
    version="1.0.0",
    label="Calendar",
    description="Calendar items synchronized with project work.",
    always_enabled=True,
    dependencies=("identity_access", "projects"),
    backend_router_keys=("calendar",),
    nav_entries=(
        NavEntry(label="Calendar", path="/calendar", group="workspace", icon="calendar"),
    ),
    frontend_routes=(FrontendRoute(path="/calendar", page_key="calendar.main"),),
)
