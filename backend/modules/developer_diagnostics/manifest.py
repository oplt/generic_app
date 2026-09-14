from backend.modules.manifests.types import ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="developer_diagnostics",
    version="1.0.0",
    label="Developer diagnostics",
    description="Per-request developer diagnostics panel (flag-gated, shell-embedded).",
    always_enabled=False,
    optional=False,
    user_visible=False,
    surface=ModuleSurface.EMBEDDED,
    embedding_host="app.shell",
    dependencies=("observability",),
    backend_router_keys=("developer_diagnostics",),
    required_permissions=("diagnostics.read",),
)
