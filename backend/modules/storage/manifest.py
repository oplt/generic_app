from backend.modules.manifests.types import ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="storage",
    version="1.0.0",
    label="Storage",
    description=(
        "Object/file storage used by document and upload workflows. "
        "Internal infrastructure; compact health chips on Admin Platform "
        "(platform.admin / features/platform-admin) — never credentials."
    ),
    always_enabled=True,
    user_visible=False,
    surface=ModuleSurface.INTERNAL,
    # Readiness for object storage is declared by dependents (e.g. rag), not
    # by this always-on infrastructure module — keeps core/lean profiles soft.
    health_checks=(),
    database_requirements=(),
)
