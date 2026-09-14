from backend.modules.manifests.types import ModuleManifest

MANIFEST = ModuleManifest(
    key="orders",
    version="1.0.0",
    label="Orders",
    description="Orders module scaffolded by generic-app create-module.",
    always_enabled=True,
    optional=False,
    dependencies=('identity_access', 'storage'),
    backend_router_keys=("orders",),
    celery_queues=("orders",),
    required_permissions=('orders.read', 'orders.manage'),
    health_checks=("storage",),
    database_requirements=("orders",),
)
