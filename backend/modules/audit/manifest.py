from backend.modules.manifests.types import ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="audit",
    version="1.0.0",
    label="Audit",
    description=(
        "Cross-cutting audit log persistence used by admin and mutating "
        "platform/settings/users routes. Backend/internal — no standalone UI."
    ),
    always_enabled=True,
    user_visible=False,
    surface=ModuleSurface.INTERNAL,
    dependencies=("identity_access",),
    database_requirements=("audit_logs",),
)
