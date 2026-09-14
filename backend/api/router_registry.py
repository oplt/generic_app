"""Declarative FastAPI router contributions keyed by ``backend_router_keys``.

Bootstrap mounts only contributions whose owning module is in the active
capability profile resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from fastapi import APIRouter

from backend.modules.manifests import get_manifest_map
from backend.modules.platform.profiles import resolve_active_modules


@dataclass(frozen=True, slots=True)
class RouterContribution:
    key: str
    import_path: str
    attr: str = "router"
    prefix: str | None = None
    tags: tuple[str, ...] = ()


# Intentional allow-list: router_key → how to mount it.
ROUTER_CONTRIBUTIONS: dict[str, RouterContribution] = {
    "auth": RouterContribution(
        key="auth",
        import_path="backend.modules.identity_access.router",
        prefix="/auth",
        tags=("auth",),
    ),
    "ai": RouterContribution(
        key="ai",
        import_path="backend.modules.ai.router",
        prefix="/ai",
        tags=("ai",),
    ),
    "agent": RouterContribution(
        key="agent",
        import_path="backend.modules.ai.agent_router",
        prefix="/agent",
        tags=("agent",),
    ),
    "memory": RouterContribution(
        key="memory",
        import_path="backend.modules.memory.api.routes",
        prefix="/memory",
        tags=("memory",),
    ),
    "rag": RouterContribution(
        key="rag",
        import_path="backend.modules.rag.api.routes",
        prefix="/rag",
        tags=("rag",),
    ),
    "chat": RouterContribution(
        key="chat",
        import_path="backend.modules.chat.router",
        prefix="/chat",
        tags=("chat",),
    ),
    "calendar": RouterContribution(
        key="calendar",
        import_path="backend.modules.calendar.router",
        prefix="/calendar",
        tags=("calendar",),
    ),
    "users": RouterContribution(
        key="users",
        import_path="backend.modules.users.router",
        prefix="/users",
        tags=("users",),
    ),
    "profile": RouterContribution(
        key="profile",
        import_path="backend.modules.profile.router",
        prefix="/profile",
        tags=("profile",),
    ),
    "projects": RouterContribution(
        key="projects",
        import_path="backend.modules.projects.router",
        prefix="/projects",
        tags=("projects",),
    ),
    "notifications": RouterContribution(
        key="notifications",
        import_path="backend.modules.notifications.router",
        prefix="/notifications",
        tags=("notifications",),
    ),
    "observability": RouterContribution(
        key="observability",
        import_path="backend.observability.router",
        prefix="/observability",
        tags=("observability",),
    ),
    "platform": RouterContribution(
        key="platform",
        import_path="backend.modules.platform.router",
        prefix="/platform",
        tags=("platform",),
    ),
    "policy": RouterContribution(
        key="policy",
        import_path="backend.modules.policy.router",
        prefix="/policy",
        tags=("policy",),
    ),
    "settings": RouterContribution(
        key="settings",
        import_path="backend.modules.settings.router",
        prefix="/settings",
        tags=("settings",),
    ),
    "admin": RouterContribution(
        key="admin",
        import_path="backend.modules.admin.router",
        prefix="/admin",
        tags=("admin",),
    ),
    "jobs": RouterContribution(
        key="jobs",
        import_path="backend.modules.jobs.router",
        prefix="/admin",
        tags=("jobs",),
    ),
    "diagnostics": RouterContribution(
        key="diagnostics",
        import_path="backend.modules.diagnostics.router",
        prefix="/admin",
        tags=("diagnostics",),
    ),
    "developer_diagnostics": RouterContribution(
        key="developer_diagnostics",
        import_path="backend.modules.developer_diagnostics.router",
        prefix=None,
        tags=("developer-diagnostics",),
    ),
    # <generic-app:router-contributions>
    # </generic-app:router-contributions>
}


def active_router_keys(
    active_modules: set[str] | frozenset[str] | tuple[str, ...],
) -> tuple[str, ...]:
    enabled = set(active_modules)
    keys: list[str] = []
    by_key = get_manifest_map()
    for module_key in sorted(enabled):
        manifest = by_key.get(module_key)
        if manifest is None:
            continue
        keys.extend(manifest.backend_router_keys)
    # Preserve declaration order from ROUTER_CONTRIBUTIONS for stable mounting.
    ordered = [key for key in ROUTER_CONTRIBUTIONS if key in set(keys)]
    unknown = set(keys) - set(ROUTER_CONTRIBUTIONS)
    if unknown:
        raise RuntimeError(f"Manifest declares unknown backend_router_keys: {sorted(unknown)}")
    return tuple(ordered)


def _load_router(contribution: RouterContribution) -> APIRouter:
    module = import_module(contribution.import_path)
    router = getattr(module, contribution.attr)
    if not isinstance(router, APIRouter):
        raise RuntimeError(
            f"Router contribution {contribution.key!r} did not resolve to APIRouter"
        )
    return router


def build_api_router(
    *,
    active_modules: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    profile: str | None = None,
) -> APIRouter:
    """Build `/api/v1` router for the resolved active module set."""

    if active_modules is None:
        resolution = resolve_active_modules(profile)
        active_modules = resolution.active_modules

    api_router = APIRouter(prefix="/api/v1")
    for key in active_router_keys(active_modules):
        contribution = ROUTER_CONTRIBUTIONS[key]
        include_kwargs: dict[str, object] = {"tags": list(contribution.tags)}
        if contribution.prefix is not None:
            include_kwargs["prefix"] = contribution.prefix
        api_router.include_router(_load_router(contribution), **include_kwargs)
    return api_router


__all__ = [
    "ROUTER_CONTRIBUTIONS",
    "RouterContribution",
    "active_router_keys",
    "build_api_router",
]
