from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="ai",
    version="1.0.0",
    label="AI",
    description="Prompt ops, providers, reviews, and evaluations.",
    always_enabled=True,
    dependencies=("identity_access", "storage"),
    backend_router_keys=("ai", "agent"),
    celery_queues=("ai", "evaluation"),
    database_requirements=("ai_runs", "prompt_templates"),
)
