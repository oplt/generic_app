from backend.modules.manifests.types import FrontendRoute, ModuleManifest, NavEntry

MANIFEST = ModuleManifest(
    key="identity_access",
    version="1.0.0",
    label="Identity & Access",
    description="Authentication, sessions, organizations, and memberships.",
    always_enabled=True,
    backend_router_keys=("auth",),
    required_permissions=(),
    database_requirements=("users", "organizations", "organization_memberships", "refresh_sessions"),
    frontend_routes=(
        FrontendRoute(path="/login", page_key="auth.login"),
        FrontendRoute(path="/signup", page_key="auth.signup"),
    ),
)
