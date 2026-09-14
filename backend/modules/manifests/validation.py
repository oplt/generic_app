"""Manifest discovery errors and dependency validation."""

from __future__ import annotations

from backend.modules.manifests.types import ModuleManifest


class ModuleManifestError(RuntimeError):
    """Raised when module manifests are inconsistent or dependencies are missing."""


def index_manifests(manifests: tuple[ModuleManifest, ...]) -> dict[str, ModuleManifest]:
    by_key: dict[str, ModuleManifest] = {}
    for manifest in manifests:
        if manifest.key in by_key:
            raise ModuleManifestError(f"Duplicate module manifest key: {manifest.key}")
        by_key[manifest.key] = manifest
    return by_key


def validate_manifest_graph(manifests: tuple[ModuleManifest, ...]) -> None:
    """Ensure every declared dependency refers to a registered module."""

    by_key = index_manifests(manifests)
    for manifest in manifests:
        for dependency in manifest.dependencies:
            if dependency not in by_key:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} depends on unknown module {dependency!r}"
                )
            if dependency == manifest.key:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} cannot depend on itself"
                )
    _assert_no_cycles(by_key)


def _assert_no_cycles(by_key: dict[str, ModuleManifest]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visited:
            return
        if key in visiting:
            raise ModuleManifestError(f"Module dependency cycle involving {key!r}")
        visiting.add(key)
        for dependency in by_key[key].dependencies:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)

    for key in by_key:
        visit(key)


def resolve_effective_modules(
    *,
    manifests: tuple[ModuleManifest, ...],
    enabled_optional: set[str] | list[str],
) -> set[str]:
    """Return always-on modules plus enabled optional modules after dependency checks.

    Pack lists may still mention always-on modules for documentation; those entries
    are ignored. Unknown keys fail clearly.
    """

    by_key = index_manifests(manifests)
    requested = set(enabled_optional)
    unknown = requested - set(by_key)
    if unknown:
        raise ModuleManifestError(
            "Unknown module(s) in pack/overrides: " + ", ".join(sorted(unknown))
        )

    enabled = {key for key, manifest in by_key.items() if manifest.always_enabled}
    optional_requested = {key for key in requested if by_key[key].optional}
    enabled |= optional_requested

    missing: list[str] = []
    for key in sorted(enabled):
        for dependency in by_key[key].dependencies:
            if dependency not in enabled:
                missing.append(f"{key} -> {dependency}")
    if missing:
        raise ModuleManifestError(
            "Enabled module is missing required dependencies: " + "; ".join(missing)
        )
    return enabled


def optional_catalog(
    manifests: tuple[ModuleManifest, ...],
) -> tuple[dict[str, object], ...]:
    """Shape compatible with legacy MODULE_CATALOG entries."""

    items: list[dict[str, object]] = []
    for manifest in manifests:
        if not manifest.optional:
            continue
        items.append(
            {
                "key": manifest.key,
                "label": manifest.label,
                "description": manifest.description,
                "user_visible": manifest.user_visible,
            }
        )
    return tuple(items)
