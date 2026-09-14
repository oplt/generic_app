from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="platform",
    version="1.0.0",
    label="Platform",
    description=(
        "Platform configuration, module packs, and shared platform APIs. "
        "User workspace: features/platform (platform.workspace); "
        "admin console: features/platform-admin (platform.admin)."
    ),
    always_enabled=True,
    surface=ModuleSurface.USER_FACING,
    dependencies=("identity_access", "settings"),
    backend_router_keys=("platform",),
    settings_prefixes=("platform.",),
    database_requirements=(
        "subscription_plans",
        "feature_flags",
        "webhook_endpoints",
        "api_keys",
        "email_templates",
    ),
    frontend_routes=(
        FrontendRoute(path="/platform", page_key="platform.workspace"),
        FrontendRoute(path="/admin/platform", page_key="platform.admin"),
    ),
)
