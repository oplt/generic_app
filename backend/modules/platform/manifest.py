from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="platform",
    version="1.0.0",
    label="Platform",
    description="Platform configuration, module packs, and shared platform APIs.",
    always_enabled=True,
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
)
