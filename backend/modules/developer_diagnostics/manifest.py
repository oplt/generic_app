from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="developer_diagnostics",
    version="1.0.0",
    label="Developer diagnostics",
    description="Per-request developer diagnostics panel (flag-gated).",
    always_enabled=True,
    dependencies=("observability",),
    backend_router_keys=("developer_diagnostics",),
    required_permissions=("diagnostics.read",),
)
