"""Patch intentional registry / router / alembic / policy catalog wiring."""

from __future__ import annotations

from pathlib import Path

from backend.tools.generic_app.naming import ModuleNames


class WiringError(RuntimeError):
    """Raised when an intentional registration file cannot be patched safely."""


def wire_manifest_registry(registry_path: Path, names: ModuleNames) -> bool:
    """Insert manifest import + REGISTERED_MANIFESTS entry. Returns True if changed."""

    text = registry_path.read_text(encoding="utf-8")
    import_line = (
        f"from backend.modules.{names.key}.manifest import MANIFEST as {names.constant}\n"
    )
    if import_line in text:
        return False

    # Keep imports sorted-ish: insert before OPTIONAL_PLATFORM import block end /
    # after last `from backend.modules` manifest import before REGISTERED_MANIFESTS.
    anchor = "from backend.observability.manifest import MANIFEST as OBSERVABILITY\n"
    if anchor not in text:
        raise WiringError("Could not locate observability manifest import for wiring")
    text = text.replace(anchor, anchor + import_line, 1)

    entry = f"    {names.constant},\n"
    tuple_anchor = "    MEMORY,\n    *OPTIONAL_PLATFORM_MANIFESTS,\n"
    if tuple_anchor not in text:
        raise WiringError("Could not locate REGISTERED_MANIFESTS insertion point")
    text = text.replace(
        tuple_anchor,
        f"    MEMORY,\n{entry}    *OPTIONAL_PLATFORM_MANIFESTS,\n",
        1,
    )
    registry_path.write_text(text, encoding="utf-8")
    return True


def wire_api_router(router_path: Path, names: ModuleNames) -> bool:
    text = router_path.read_text(encoding="utf-8")
    import_line = (
        f"from backend.modules.{names.key}.api.router import router as {names.key}_router\n"
    )
    include_line = (
        f'api_router.include_router({names.key}_router, prefix="/{names.key}", '
        f'tags=["{names.key}"])\n'
    )
    if include_line in text:
        return False

    # Insert import among module imports (after settings import is fine).
    settings_import = (
        "from backend.modules.settings.router import router as settings_router\n"
    )
    if settings_import not in text:
        raise WiringError("Could not locate settings router import for wiring")
    text = text.replace(settings_import, settings_import + import_line, 1)

    admin_include = (
        'api_router.include_router(admin_router, prefix="/admin", tags=["admin"])\n'
    )
    if admin_include not in text:
        raise WiringError("Could not locate admin router include for wiring")
    text = text.replace(admin_include, include_line + admin_include, 1)
    router_path.write_text(text, encoding="utf-8")
    return True


def wire_alembic_env(env_path: Path, names: ModuleNames) -> bool:
    text = env_path.read_text(encoding="utf-8")
    import_line = (
        f"from backend.modules.{names.key}.infrastructure import models as "
        f"{names.key}_models  # noqa: F401\n"
    )
    if import_line in text:
        return False
    anchor = "from backend.modules.users import models as user_models  # noqa: F401\n"
    if anchor not in text:
        raise WiringError("Could not locate alembic users model import for wiring")
    text = text.replace(anchor, anchor + import_line, 1)
    env_path.write_text(text, encoding="utf-8")
    return True


def wire_policy_catalog(catalog_path: Path, names: ModuleNames) -> bool:
    """Append permission constants + ALL_PERMISSIONS entries."""

    text = catalog_path.read_text(encoding="utf-8")
    read_const = f'{names.constant}_READ = "{names.permission_prefix}.read"'
    manage_const = f'{names.constant}_MANAGE = "{names.permission_prefix}.manage"'
    if read_const in text:
        return False

    # Insert constants before ALL_PERMISSIONS.
    anchor = "ALL_PERMISSIONS: tuple[str, ...] = ("
    if anchor not in text:
        raise WiringError("Could not locate ALL_PERMISSIONS for wiring")
    constants = (
        f"\n{read_const}\n{manage_const}\n"
    )
    text = text.replace(anchor, constants + anchor, 1)

    # Insert into ALL_PERMISSIONS tuple before closing.
    # Prefer after ADMIN_MANAGE,
    admin_entry = "    ADMIN_MANAGE,\n)"
    if admin_entry not in text:
        raise WiringError("Could not locate ADMIN_MANAGE in ALL_PERMISSIONS")
    text = text.replace(
        admin_entry,
        f"    ADMIN_MANAGE,\n    {names.constant}_READ,\n    {names.constant}_MANAGE,\n)",
        1,
    )
    catalog_path.write_text(text, encoding="utf-8")
    return True
