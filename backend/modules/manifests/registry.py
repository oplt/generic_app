"""Intentional application module manifest registry.

Modules are registered explicitly here. Do not scan the filesystem or execute
untrusted code to discover manifests.
"""

from __future__ import annotations

from backend.modules.admin.manifest import MANIFEST as ADMIN
from backend.modules.ai.manifest import MANIFEST as AI
from backend.modules.calendar.manifest import MANIFEST as CALENDAR
from backend.modules.chat.manifest import MANIFEST as CHAT
from backend.modules.developer_diagnostics.manifest import MANIFEST as DEVELOPER_DIAGNOSTICS
from backend.modules.diagnostics.manifest import MANIFEST as DIAGNOSTICS
from backend.modules.identity_access.manifest import MANIFEST as IDENTITY_ACCESS
from backend.modules.jobs.manifest import MANIFEST as JOBS
from backend.modules.manifests.types import ModuleManifest, NavEntry
from backend.modules.manifests.validation import (
    ModuleManifestError,
    index_manifests,
    optional_catalog,
    resolve_effective_modules,
    validate_manifest_graph,
)
from backend.modules.memory.manifest import MANIFEST as MEMORY
from backend.modules.notifications.manifest import MANIFEST as NOTIFICATIONS
from backend.modules.platform.manifest import MANIFEST as PLATFORM
from backend.modules.platform.optional_manifests import OPTIONAL_PLATFORM_MANIFESTS
from backend.modules.policy.manifest import MANIFEST as POLICY
from backend.modules.profile.manifest import MANIFEST as PROFILE
from backend.modules.projects.manifest import MANIFEST as PROJECTS
from backend.modules.rag.manifest import MANIFEST as RAG
from backend.modules.settings.manifest import MANIFEST as SETTINGS
from backend.modules.storage.manifest import MANIFEST as STORAGE
from backend.modules.users.manifest import MANIFEST as USERS
from backend.observability.manifest import MANIFEST as OBSERVABILITY

# <generic-app:manifest-imports>
# </generic-app:manifest-imports>

# Order is documentary only; dependency validation is graph-based.
REGISTERED_MANIFESTS: tuple[ModuleManifest, ...] = (
    STORAGE,
    IDENTITY_ACCESS,
    USERS,
    PROFILE,
    PROJECTS,
    SETTINGS,
    PLATFORM,
    POLICY,
    OBSERVABILITY,
    NOTIFICATIONS,
    CALENDAR,
    ADMIN,
    JOBS,
    DIAGNOSTICS,
    DEVELOPER_DIAGNOSTICS,
    AI,
    RAG,
    CHAT,
    MEMORY,
    # <generic-app:manifest-entries>
    # </generic-app:manifest-entries>
    *OPTIONAL_PLATFORM_MANIFESTS,
)


def get_registered_manifests() -> tuple[ModuleManifest, ...]:
    return REGISTERED_MANIFESTS


def get_manifest_map() -> dict[str, ModuleManifest]:
    return index_manifests(REGISTERED_MANIFESTS)


def validate_registry() -> None:
    """Fail startup when the intentional registry is inconsistent."""

    validate_manifest_graph(REGISTERED_MANIFESTS)


def effective_modules(
    enabled_optional: set[str] | list[str] = (),
    *,
    enabled_selected: set[str] | list[str] = (),
) -> set[str]:
    return resolve_effective_modules(
        manifests=REGISTERED_MANIFESTS,
        enabled_optional=enabled_optional,
        enabled_selected=enabled_selected,
    )


def catalog_definitions() -> tuple[dict[str, object], ...]:
    return optional_catalog(REGISTERED_MANIFESTS)


def nav_entries_for_modules(module_keys: set[str] | list[str]) -> list[dict[str, str | None]]:
    """Serialize nav contributions for enabled modules (frontend allow-list)."""

    enabled = set(module_keys)
    entries: list[dict[str, str | None]] = []
    for manifest in REGISTERED_MANIFESTS:
        if manifest.key not in enabled:
            continue
        for entry in manifest.nav_entries:
            entries.append(
                {
                    "module_key": manifest.key,
                    "label": entry.label,
                    "path": entry.path,
                    "group": entry.group,
                    "icon": entry.icon,
                    "required_permission": entry.required_permission,
                    "feature_flag": entry.feature_flag,
                }
            )
    return entries


def frontend_routes_for_modules(
    module_keys: set[str] | list[str],
) -> list[dict[str, str | None]]:
    enabled = set(module_keys)
    routes: list[dict[str, str | None]] = []
    for manifest in REGISTERED_MANIFESTS:
        if manifest.key not in enabled:
            continue
        for route in manifest.frontend_routes:
            routes.append(
                {
                    "module_key": manifest.key,
                    "path": route.path,
                    "page_key": route.page_key,
                    "required_permission": route.required_permission,
                    "feature_flag": route.feature_flag,
                }
            )
    return routes


__all__ = [
    "ModuleManifestError",
    "NavEntry",
    "REGISTERED_MANIFESTS",
    "catalog_definitions",
    "effective_modules",
    "frontend_routes_for_modules",
    "get_manifest_map",
    "get_registered_manifests",
    "nav_entries_for_modules",
    "validate_registry",
]
