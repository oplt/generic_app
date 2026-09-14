from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface

MANIFEST = ModuleManifest(
    key="ai",
    version="1.0.0",
    label="AI",
    description="Prompt ops, providers, reviews, and evaluations.",
    always_enabled=False,
    optional=False,
    surface=ModuleSurface.USER_FACING,
    dependencies=("identity_access", "storage"),
    backend_router_keys=("ai", "agent"),
    celery_queues=("ai", "evaluation"),
    database_requirements=("ai_runs", "prompt_templates"),
    frontend_routes=(FrontendRoute(path="/ai", page_key="ai.studio"),),
)
