from backend.modules.manifests.types import FrontendRoute, ModuleManifest, ModuleSurface, NavEntry

MANIFEST = ModuleManifest(
    key="projects",
    version="1.0.0",
    label="Projects",
    description="Core project and task workspace.",
    always_enabled=True,
    surface=ModuleSurface.USER_FACING,
    dependencies=("identity_access",),
    backend_router_keys=("projects",),
    required_permissions=("project.read", "project.create", "project.update", "project.delete"),
    database_requirements=("projects", "project_tasks"),
    nav_entries=(
        NavEntry(
            label="Projects",
            path="/projects",
            group="workspace",
            icon="projects",
            required_permission="project.read",
        ),
    ),
    frontend_routes=(
        FrontendRoute(path="/projects", page_key="projects.list"),
        FrontendRoute(path="/projects/:projectId", page_key="projects.detail"),
    ),
)
