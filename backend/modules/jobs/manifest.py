from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="jobs",
    version="1.0.0",
    label="Jobs",
    description="Operational background jobs console.",
    always_enabled=True,
    dependencies=("policy", "rag"),
    backend_router_keys=("jobs",),
    required_permissions=("jobs.read", "jobs.retry", "jobs.cancel"),
)
