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
    enabled_optional: set[str] | list[str] = (),
    enabled_selected: set[str] | list[str] = (),
    close_dependencies: bool = True,
) -> set[str]:
    """Return always-on ∪ profile-selected ∪ optional modules.

    * ``enabled_optional`` — pack/catalog toggles (``manifest.optional``).
    * ``enabled_selected`` — profile-selected specialists (available but not
      always-on and not pack toggles), e.g. ``ai`` / ``rag`` / ``chat``.
    * When ``close_dependencies`` is true, required dependencies are pulled in
      automatically so profiles can list leaf modules without repeating the
      full graph.
    """

    by_key = index_manifests(manifests)
    known = set(by_key)

    requested_optional = set(enabled_optional)
    requested_selected = set(enabled_selected)
    unknown = (requested_optional | requested_selected) - known
    if unknown:
        raise ModuleManifestError(
            "Unknown module(s) in pack/overrides/profile: " + ", ".join(sorted(unknown))
        )

    enabled = {key for key, manifest in by_key.items() if manifest.always_enabled}

    for key in requested_optional:
        manifest = by_key[key]
        if manifest.always_enabled:
            # Packs may document always-on modules; ignore.
            continue
        if not manifest.optional:
            raise ModuleManifestError(
                f"Module {key!r} is not an optional pack toggle; "
                "enable it via capability profile modules instead"
            )
        enabled.add(key)

    for key in requested_selected:
        manifest = by_key[key]
        if manifest.always_enabled:
            continue
        if manifest.optional:
            # Optional catalog keys may also appear in profile.modules; allow.
            enabled.add(key)
            continue
        enabled.add(key)

    if close_dependencies:
        enabled = _close_dependencies(by_key, enabled)
    else:
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


def _close_dependencies(
    by_key: dict[str, ModuleManifest],
    seeds: set[str],
) -> set[str]:
    enabled = set(seeds)
    pending = list(seeds)
    while pending:
        key = pending.pop()
        for dependency in by_key[key].dependencies:
            if dependency not in enabled:
                if dependency not in by_key:
                    raise ModuleManifestError(
                        f"Module {key!r} depends on unknown module {dependency!r}"
                    )
                enabled.add(dependency)
                pending.append(dependency)
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
