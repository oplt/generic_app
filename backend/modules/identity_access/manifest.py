from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="identity_access",
    version="1.0.0",
    label="Identity & Access",
    description="Authentication, sessions, organizations, and memberships.",
    always_enabled=True,
    surface=ModuleSurface.USER_FACING,
    backend_router_keys=("auth",),
    required_permissions=(),
    database_requirements=(
        "users",
        "organizations",
        "organization_memberships",
        "refresh_sessions",
    ),
    frontend_routes=(
        FrontendRoute(path="/", page_key="auth.home"),
        FrontendRoute(path="/reset-password", page_key="auth.reset_password"),
        FrontendRoute(path="/verify-email", page_key="auth.verify_email"),
    ),
)
