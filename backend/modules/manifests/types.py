"""Typed module manifest definitions.

Manifests are internal application metadata, not a plugin marketplace.
Import them through the intentional registry only — never exec untrusted code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ModuleSurface(StrEnum):
    """How a module is meant to appear in the product.

    Explicit categories replace guessing from empty ``frontend_routes`` tuples.
    """

    USER_FACING = "user_facing"
    ADMIN_FACING = "admin_facing"
    EMBEDDED = "embedded"
    API_ONLY = "api_only"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class NavEntry:
    """Frontend navigation contribution."""

    label: str
    path: str
    group: str = "workspace"
    icon: str | None = None
    required_permission: str | None = None
    feature_flag: str | None = None
    module_key: str | None = None  # filled by registry when omitted


@dataclass(frozen=True, slots=True)
class FrontendRoute:
    """Declarative frontend route metadata (page_key is an intentional allow-list id)."""

    path: str
    page_key: str
    required_permission: str | None = None
    feature_flag: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Declarative description of one application module."""

    key: str
    version: str
    label: str
    description: str
    dependencies: tuple[str, ...] = ()
    always_enabled: bool = False
    optional: bool = True
    user_visible: bool = True
    surface: ModuleSurface = ModuleSurface.USER_FACING
    # Host page_key or stable host id when surface=EMBEDDED (e.g. app.shell, admin.platform).
    embedding_host: str | None = None
    backend_router_keys: tuple[str, ...] = ()
    celery_queues: tuple[str, ...] = ()
    scheduled_tasks: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    settings_prefixes: tuple[str, ...] = ()
    feature_flags: tuple[str, ...] = ()
    health_checks: tuple[str, ...] = ()
    database_requirements: tuple[str, ...] = ()
    nav_entries: tuple[NavEntry, ...] = ()
    frontend_routes: tuple[FrontendRoute, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.key or not self.key.replace("_", "").isalnum():
            raise ValueError(f"invalid module key: {self.key!r}")
        if self.always_enabled and self.optional:
            # Always-on modules are part of the core graph, not pack toggles.
            object.__setattr__(self, "optional", False)
        if isinstance(self.surface, str) and not isinstance(self.surface, ModuleSurface):
            object.__setattr__(self, "surface", ModuleSurface(self.surface))
