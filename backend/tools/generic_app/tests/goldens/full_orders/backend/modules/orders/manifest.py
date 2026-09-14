from backend.modules.manifests.types import FrontendRoute, ModuleManifest, NavEntry

MANIFEST = ModuleManifest(
    key="orders",
    version="1.0.0",
    label="Orders",
    description="Orders module scaffolded by generic-app create-module.",
    always_enabled=False,
    optional=True,
    dependencies=('identity_access', 'storage'),
    backend_router_keys=("orders",),
    celery_queues=("orders",),
    required_permissions=('orders.read', 'orders.manage'),
    health_checks=("storage",),
    database_requirements=("orders",),
    nav_entries=(
        NavEntry(
            label="Orders",
            path="/orders",
            group="workspace",
            icon="orders",
            required_permission="orders.read",
        ),
    ),
    frontend_routes=(
        FrontendRoute(
            path="/orders",
            page_key="orders.list",
            required_permission="orders.read",
        ),
    ),
)
