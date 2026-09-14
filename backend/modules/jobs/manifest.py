from backend.modules.manifests.types import FrontendRoute, ModuleManifest

MANIFEST = ModuleManifest(
    key="jobs",
    version="1.0.0",
    label="Jobs",
    description="Operational background jobs console.",
    always_enabled=False,
    optional=False,
    dependencies=("policy", "rag"),
    backend_router_keys=("jobs",),
    required_permissions=("jobs.read", "jobs.retry", "jobs.cancel"),
    frontend_routes=(FrontendRoute(path="/admin/jobs", page_key="jobs.admin.console"),),
)
