"""Optional platform capability manifests (pack-togglable)."""

from backend.modules.manifests.types import ModuleManifest, ModuleSurface

BILLING = ModuleManifest(
    key="billing",
    version="1.0.0",
    label="Billing",
    description="Plan catalog and subscription management.",
    optional=True,
    user_visible=True,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="platform.admin",
    dependencies=("platform", "identity_access"),
    backend_router_keys=("platform",),
    required_permissions=("billing.read", "billing.manage"),
    feature_flags=("advanced_billing_controls",),
)

API_KEYS = ModuleManifest(
    key="api_keys",
    version="1.0.0",
    label="API Keys",
    description="User-managed credentials for integrations and automation.",
    optional=True,
    user_visible=True,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="platform.admin",
    dependencies=("platform", "identity_access"),
    backend_router_keys=("platform",),
    required_permissions=("api_keys.manage",),
)

WEBHOOKS = ModuleManifest(
    key="webhooks",
    version="1.0.0",
    label="Webhooks",
    description="Outbound event delivery to external systems.",
    optional=True,
    user_visible=True,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="platform.admin",
    dependencies=("platform", "identity_access"),
    backend_router_keys=("platform",),
    required_permissions=("webhooks.manage",),
    feature_flags=("webhook_replay",),
)

FEATURE_FLAGS = ModuleManifest(
    key="feature_flags",
    version="1.0.0",
    label="Feature Flags",
    description="Runtime rollout controls for features and experiments.",
    optional=True,
    user_visible=True,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="platform.admin",
    dependencies=("platform",),
    backend_router_keys=("platform",),
    feature_flags=("beta_dashboard",),
)

EMAIL_TEMPLATES = ModuleManifest(
    key="email_templates",
    version="1.0.0",
    label="Email Templates",
    description="Customizable transactional email content.",
    optional=True,
    user_visible=False,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="platform.admin",
    dependencies=("platform",),
    backend_router_keys=("platform",),
)

OPTIONAL_PLATFORM_MANIFESTS: tuple[ModuleManifest, ...] = (
    BILLING,
    API_KEYS,
    WEBHOOKS,
    FEATURE_FLAGS,
    EMAIL_TEMPLATES,
)
