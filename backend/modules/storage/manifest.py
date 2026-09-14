from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="storage",
    version="1.0.0",
    label="Storage",
    description="Object/file storage used by document and upload workflows.",
    always_enabled=True,
    health_checks=("storage",),
    database_requirements=(),
)
