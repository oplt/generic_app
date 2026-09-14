"""Application module manifest system."""

from backend.modules.manifests.registry import (
    REGISTERED_MANIFESTS,
    catalog_definitions,
    effective_modules,
    frontend_routes_for_modules,
    get_manifest_map,
    get_registered_manifests,
    nav_entries_for_modules,
    validate_registry,
)
from backend.modules.manifests.types import FrontendRoute, ModuleManifest, NavEntry
from backend.modules.manifests.validation import ModuleManifestError

__all__ = [
    "FrontendRoute",
    "ModuleManifest",
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
