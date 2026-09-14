"""Manifest discovery errors and dependency validation."""

from __future__ import annotations

from backend.modules.manifests.types import ModuleManifest, ModuleSurface


class ModuleManifestError(RuntimeError):
    """Raised when module manifests are inconsistent or dependencies are missing."""


def index_manifests(manifests: tuple[ModuleManifest, ...]) -> dict[str, ModuleManifest]:
    by_key: dict[str, ModuleManifest] = {}
    for manifest in manifests:
        if manifest.key in by_key:
            raise ModuleManifestError(f"Duplicate module manifest key: {manifest.key}")
        by_key[manifest.key] = manifest
    return by_key


def validate_manifest_graph(
    manifests: tuple[ModuleManifest, ...],
    *,
    router_keys: set[str] | frozenset[str] | None = None,
    known_page_keys: set[str] | frozenset[str] | None = None,
) -> None:
    """Ensure manifests form a consistent capability graph.

    Optional ``router_keys`` / ``known_page_keys`` enable contract checks against
    ``ROUTER_CONTRIBUTIONS`` and the frontend page-key allow-list.
    """

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
    _assert_surface_rules(manifests)
    _assert_nav_routes_resolve(manifests)
    if router_keys is not None:
        _assert_router_keys(manifests, set(router_keys))
    if known_page_keys is not None:
        _assert_page_keys(manifests, set(known_page_keys))


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


def _assert_surface_rules(manifests: tuple[ModuleManifest, ...]) -> None:
    for manifest in manifests:
        surface = manifest.surface
        has_routes = bool(manifest.frontend_routes)
        has_nav = bool(manifest.nav_entries)
        has_host = bool(manifest.embedding_host)

        if surface in {ModuleSurface.INTERNAL, ModuleSurface.API_ONLY}:
            if has_nav:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} surface={surface.value} "
                    "must not declare nav_entries"
                )
            if has_routes:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} surface={surface.value} "
                    "must not declare frontend_routes"
                )
            if has_host:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} surface={surface.value} "
                    "must not declare embedding_host"
                )
            if manifest.user_visible and surface == ModuleSurface.INTERNAL:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} INTERNAL surface requires user_visible=False"
                )

        if surface == ModuleSurface.EMBEDDED:
            if not has_host:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} EMBEDDED surface requires embedding_host"
                )
            if has_nav:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} EMBEDDED surface must not declare primary nav_entries"
                )

        if (
            surface in {ModuleSurface.USER_FACING, ModuleSurface.ADMIN_FACING}
            and not has_routes
            and not has_host
        ):
            raise ModuleManifestError(
                f"Module {manifest.key!r} surface={surface.value} requires "
                "frontend_routes or embedding_host"
            )


def _assert_nav_routes_resolve(manifests: tuple[ModuleManifest, ...]) -> None:
    known_paths = {
        route.path
        for manifest in manifests
        for route in manifest.frontend_routes
    }
    for manifest in manifests:
        for entry in manifest.nav_entries:
            if entry.path not in known_paths:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} nav path {entry.path!r} "
                    "does not match any declared frontend_route.path"
                )


def _assert_router_keys(
    manifests: tuple[ModuleManifest, ...],
    router_keys: set[str],
) -> None:
    for manifest in manifests:
        unknown = set(manifest.backend_router_keys) - router_keys
        if unknown:
            raise ModuleManifestError(
                f"Module {manifest.key!r} declares unknown backend_router_keys: "
                + ", ".join(sorted(unknown))
            )


def _assert_page_keys(
    manifests: tuple[ModuleManifest, ...],
    known_page_keys: set[str],
) -> None:
    for manifest in manifests:
        for route in manifest.frontend_routes:
            if route.page_key not in known_page_keys:
                raise ModuleManifestError(
                    f"Module {manifest.key!r} declares unknown page_key {route.page_key!r}"
                )


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
                "surface": manifest.surface.value,
            }
        )
    return tuple(items)
