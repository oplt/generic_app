"""Patch intentional registry / router / celery / frontend / alembic / policy wiring.

All patches target stable ``<generic-app:…>`` marker sections so edits are
deterministic, idempotent, and safe to re-run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.tools.generic_app.journal import MutationJournal
from backend.tools.generic_app.markers import (
    MarkerError,
    merge_line_into_marked_block,
    require_markers,
    upsert_marked_block,
)
from backend.tools.generic_app.naming import ModuleNames


class WiringError(RuntimeError):
    """Raised when an intentional registration file cannot be patched safely."""


def _write(journal: MutationJournal | None, path: Path, content: str) -> None:
    if journal is not None:
        journal.write_text(path, content)
    else:
        path.write_text(content, encoding="utf-8")


def _patch_file(
    path: Path,
    *,
    open_marker: str,
    close_marker: str,
    line: str,
    journal: MutationJournal | None,
    sort: bool = True,
) -> bool:
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = merge_line_into_marked_block(
            text,
            open_marker=open_marker,
            close_marker=close_marker,
            line=line,
            sort=sort,
        )
    except MarkerError as exc:
        raise WiringError(str(exc)) from exc
    if changed:
        _write(journal, path, new_text)
    return changed


def validate_wiring_targets(
    repo_root: Path,
    *,
    crud: bool,
    permissions: bool,
    celery: bool,
    frontend: bool,
    profile: str | None,
) -> None:
    """Fail before apply when required marker seams are missing."""

    checks: list[tuple[Path, tuple[tuple[str, str], ...]]] = [
        (
            repo_root / "backend/modules/manifests/registry.py",
            (
                ("# <generic-app:manifest-imports>", "# </generic-app:manifest-imports>"),
                ("# <generic-app:manifest-entries>", "# </generic-app:manifest-entries>"),
            ),
        ),
        (
            repo_root / "backend/api/router_registry.py",
            (
                (
                    "# <generic-app:router-contributions>",
                    "# </generic-app:router-contributions>",
                ),
            ),
        ),
    ]
    if crud:
        checks.append(
            (
                repo_root / "backend/alembic/env.py",
                (("# <generic-app:model-imports>", "# </generic-app:model-imports>"),),
            )
        )
    if permissions:
        checks.append(
            (
                repo_root / "backend/modules/policy/catalog.py",
                (
                    (
                        "# <generic-app:permission-constants>",
                        "# </generic-app:permission-constants>",
                    ),
                    (
                        "# <generic-app:permission-entries>",
                        "# </generic-app:permission-entries>",
                    ),
                ),
            )
        )
    if celery:
        checks.append(
            (
                repo_root / "backend/modules/manifests/celery_contrib.py",
                (
                    ("# <generic-app:task-routes>", "# </generic-app:task-routes>"),
                    ("# <generic-app:task-modules>", "# </generic-app:task-modules>"),
                ),
            )
        )
    if frontend:
        checks.append(
            (
                repo_root / "frontend/src/app/pageRegistry.ts",
                (
                    ("// <generic-app:page-registry>", "// </generic-app:page-registry>"),
                ),
            )
        )
        page_keys = repo_root / "frontend/src/app/pageKeys.json"
        if not page_keys.is_file():
            raise WiringError(f"Missing wiring target: {page_keys}")

    if profile:
        checks.append(
            (
                repo_root / "backend/modules/platform/profiles.py",
                (
                    (
                        "# <generic-app:profile-extra-modules>",
                        "# </generic-app:profile-extra-modules>",
                    ),
                ),
            )
        )

    for path, markers in checks:
        if not path.is_file():
            raise WiringError(f"Missing wiring target: {path}")
        try:
            require_markers(path, *markers)
        except MarkerError as exc:
            raise WiringError(str(exc)) from exc


def wire_manifest_registry(
    registry_path: Path,
    names: ModuleNames,
    *,
    journal: MutationJournal | None = None,
) -> bool:
    changed = False
    import_line = (
        f"from backend.modules.{names.key}.manifest import MANIFEST as {names.constant}"
    )
    changed |= _patch_file(
        registry_path,
        open_marker="# <generic-app:manifest-imports>",
        close_marker="# </generic-app:manifest-imports>",
        line=import_line,
        journal=journal,
    )
    changed |= _patch_file(
        registry_path,
        open_marker="# <generic-app:manifest-entries>",
        close_marker="# </generic-app:manifest-entries>",
        line=f"    {names.constant},",
        journal=journal,
    )
    return changed


def wire_router_contribution(
    registry_path: Path,
    names: ModuleNames,
    *,
    journal: MutationJournal | None = None,
) -> bool:
    line = (
        f'    "{names.key}": RouterContribution(\n'
        f'        key="{names.key}",\n'
        f'        import_path="backend.modules.{names.key}.api.router",\n'
        f'        prefix="/{names.key}",\n'
        f'        tags=("{names.key}",),\n'
        f"    ),"
    )
    # Multi-line entries cannot use simple line-sort merge. Upsert by key.
    text = registry_path.read_text(encoding="utf-8")
    open_m = "# <generic-app:router-contributions>"
    close_m = "# </generic-app:router-contributions>"
    try:
        # Drop any previous contribution for this key, then append.
        match = re.search(
            re.escape(open_m) + r"(.*?)" + re.escape(close_m),
            text,
            re.DOTALL,
        )
        if match is None:
            raise WiringError("Missing router contribution markers")
        body = match.group(1)
        # Remove existing block for this module key.
        body = re.sub(
            rf'\n    "{re.escape(names.key)}": RouterContribution\(.*?\n    \),',
            "\n",
            body,
            count=1,
            flags=re.DOTALL,
        )
        existing_lines = [ln for ln in body.splitlines() if ln.strip()]
        # Keep other multi-line contributions intact by storing as raw chunks —
        # reconstruct from remaining text + new contribution.
        cleaned = "\n".join(existing_lines)
        if cleaned.strip():
            new_body = "\n" + cleaned.rstrip() + "\n" + line + "\n"
        else:
            new_body = "\n" + line + "\n"
        # Sort by module key for stability.
        chunks = re.findall(
            r'    "[^"]+": RouterContribution\(.*?\n    \),',
            new_body,
            flags=re.DOTALL,
        )
        chunks = sorted(set(chunks), key=lambda chunk: chunk.split('"', 2)[1])
        rebuilt = "\n" + "\n".join(chunks) + "\n" if chunks else "\n"
        new_text, changed = upsert_marked_block(
            text,
            open_marker=open_m,
            close_marker=close_m,
            lines=rebuilt.strip("\n").splitlines() if rebuilt.strip() else [],
            sort=False,
        )
    except (MarkerError, WiringError) as exc:
        raise WiringError(str(exc)) from exc
    if changed:
        _write(journal, registry_path, new_text)
    return changed


def wire_alembic_env(
    env_path: Path,
    names: ModuleNames,
    *,
    journal: MutationJournal | None = None,
) -> bool:
    line = (
        f"from backend.modules.{names.key}.infrastructure import models as "
        f"{names.key}_models  # noqa: F401"
    )
    return _patch_file(
        env_path,
        open_marker="# <generic-app:model-imports>",
        close_marker="# </generic-app:model-imports>",
        line=line,
        journal=journal,
    )


def wire_policy_catalog(
    catalog_path: Path,
    names: ModuleNames,
    *,
    journal: MutationJournal | None = None,
) -> bool:
    changed = False
    changed |= _patch_file(
        catalog_path,
        open_marker="# <generic-app:permission-constants>",
        close_marker="# </generic-app:permission-constants>",
        line=f'{names.constant}_READ = "{names.permission_prefix}.read"',
        journal=journal,
    )
    changed |= _patch_file(
        catalog_path,
        open_marker="# <generic-app:permission-constants>",
        close_marker="# </generic-app:permission-constants>",
        line=f'{names.constant}_MANAGE = "{names.permission_prefix}.manage"',
        journal=journal,
    )
    changed |= _patch_file(
        catalog_path,
        open_marker="# <generic-app:permission-entries>",
        close_marker="# </generic-app:permission-entries>",
        line=f"    {names.constant}_READ,",
        journal=journal,
    )
    changed |= _patch_file(
        catalog_path,
        open_marker="# <generic-app:permission-entries>",
        close_marker="# </generic-app:permission-entries>",
        line=f"    {names.constant}_MANAGE,",
        journal=journal,
    )
    return changed


def wire_celery_contrib(
    contrib_path: Path,
    names: ModuleNames,
    *,
    journal: MutationJournal | None = None,
) -> bool:
    changed = False
    route_line = (
        f'    "{names.key}": {{"{names.key}.example_task": "{names.key}"}},'
    )
    changed |= _patch_file(
        contrib_path,
        open_marker="# <generic-app:task-routes>",
        close_marker="# </generic-app:task-routes>",
        line=route_line,
        journal=journal,
    )
    changed |= _patch_file(
        contrib_path,
        open_marker="# <generic-app:task-modules>",
        close_marker="# </generic-app:task-modules>",
        line=f'    "backend.modules.{names.key}.workers",',
        journal=journal,
    )
    return changed


def wire_profile_extra_modules(
    profiles_path: Path,
    *,
    profile_key: str,
    module_key: str,
    journal: MutationJournal | None = None,
) -> bool:
    text = profiles_path.read_text(encoding="utf-8")
    open_m = "# <generic-app:profile-extra-modules>"
    close_m = "# </generic-app:profile-extra-modules>"
    match = re.search(
        re.escape(open_m) + r"(.*?)" + re.escape(close_m),
        text,
        re.DOTALL,
    )
    if match is None:
        raise WiringError("Missing profile-extra-modules markers")

    extras: dict[str, list[str]] = {}
    for raw in match.group(1).splitlines():
        line = raw.strip().rstrip(",")
        if not line or line.startswith("#"):
            continue
        parsed = re.match(r'"([^"]+)":\s*\((.*)\)', line)
        if not parsed:
            continue
        key = parsed.group(1)
        inner = parsed.group(2).strip()
        modules = [
            part.strip().strip('"').strip("'")
            for part in inner.split(",")
            if part.strip().strip('"').strip("'")
        ]
        extras.setdefault(key, [])
        for module in modules:
            if module not in extras[key]:
                extras[key].append(module)

    bucket = extras.setdefault(profile_key, [])
    if module_key in bucket:
        return False
    bucket.append(module_key)

    lines: list[str] = []
    for key in sorted(extras):
        mods = ", ".join(f'"{item}"' for item in sorted(extras[key]))
        lines.append(f'    "{key}": ({mods},),')

    new_text, changed = upsert_marked_block(
        text,
        open_marker=open_m,
        close_marker=close_m,
        lines=lines,
        sort=False,
    )
    if changed:
        _write(journal, profiles_path, new_text)
    return changed


def wire_frontend_page_registry(
    repo_root: Path,
    names: ModuleNames,
    *,
    journal: MutationJournal | None = None,
) -> list[Path]:
    """Register page_key in pageKeys.json + pageRegistry.ts (router auto-discovers)."""

    changed_paths: list[Path] = []
    page_key = f"{names.key}.list"
    page_keys_path = repo_root / "frontend/src/app/pageKeys.json"
    keys = json.loads(page_keys_path.read_text(encoding="utf-8"))
    if not isinstance(keys, list):
        raise WiringError("pageKeys.json must be a JSON array")
    if page_key not in keys:
        keys.append(page_key)
        keys = sorted(set(keys))
        new_payload = json.dumps(keys, indent=2) + "\n"
        _write(journal, page_keys_path, new_payload)
        changed_paths.append(page_keys_path)

    registry_path = repo_root / "frontend/src/app/pageRegistry.ts"
    entry = (
        f'        page(\n'
        f'            "{page_key}",\n'
        f'            "/{names.key}",\n'
        f'            () => import("../features/{names.key}/views/{names.pascal}ListView"),\n'
        f'            {{ auth: true, moduleKey: "{names.key}" }}\n'
        f"        ),"
    )
    text = registry_path.read_text(encoding="utf-8")
    open_m = "// <generic-app:page-registry>"
    close_m = "// </generic-app:page-registry>"
    match = re.search(re.escape(open_m) + r"(.*?)" + re.escape(close_m), text, re.DOTALL)
    if match is None:
        raise WiringError("Missing page-registry markers")
    body = match.group(1)
    # Drop prior entry for this page key if present.
    body = re.sub(
        rf'\n\s*page\(\n\s*"{re.escape(page_key)}".*?\n\s*\),',
        "\n",
        body,
        count=1,
        flags=re.DOTALL,
    )
    chunks = re.findall(r"\n?\s*page\(\n.*?\n\s*\),", body, flags=re.DOTALL)
    normalized = [chunk.strip("\n") for chunk in chunks if chunk.strip()]
    normalized.append(entry)
    normalized = sorted(set(normalized), key=lambda chunk: chunk)
    new_text, registry_changed = upsert_marked_block(
        text,
        open_marker=open_m,
        close_marker=close_m,
        lines=normalized,
        sort=False,
    )
    if registry_changed:
        _write(journal, registry_path, new_text)
        changed_paths.append(registry_path)
    return changed_paths


def wire_frontend_router(
    router_path: Path,
    names: ModuleNames,
    *,
    journal: MutationJournal | None = None,
) -> bool:
    """Deprecated path kept for marker compatibility; pages wire via pageRegistry."""

    del router_path, names, journal
    return False


def apply_all_wiring(
    repo_root: Path,
    names: ModuleNames,
    *,
    crud: bool,
    permissions: bool,
    celery: bool,
    frontend: bool,
    profile: str | None,
    journal: MutationJournal | None = None,
) -> list[str]:
    """Apply every required wiring patch; return relative paths that changed."""

    validate_wiring_targets(
        repo_root,
        crud=crud,
        permissions=permissions,
        celery=celery,
        frontend=frontend,
        profile=profile,
    )
    wired: list[str] = []

    def _track(path: Path, changed: bool) -> None:
        if changed:
            wired.append(str(path.relative_to(repo_root)))

    registry = repo_root / "backend/modules/manifests/registry.py"
    _track(registry, wire_manifest_registry(registry, names, journal=journal))

    router_registry = repo_root / "backend/api/router_registry.py"
    _track(
        router_registry,
        wire_router_contribution(router_registry, names, journal=journal),
    )

    if crud:
        env_path = repo_root / "backend/alembic/env.py"
        _track(env_path, wire_alembic_env(env_path, names, journal=journal))

    if permissions:
        catalog = repo_root / "backend/modules/policy/catalog.py"
        _track(catalog, wire_policy_catalog(catalog, names, journal=journal))

    if celery:
        contrib = repo_root / "backend/modules/manifests/celery_contrib.py"
        _track(contrib, wire_celery_contrib(contrib, names, journal=journal))

    if frontend:
        for path in wire_frontend_page_registry(repo_root, names, journal=journal):
            wired.append(str(path.relative_to(repo_root)))

    if profile:
        profiles = repo_root / "backend/modules/platform/profiles.py"
        _track(
            profiles,
            wire_profile_extra_modules(
                profiles,
                profile_key=profile,
                module_key=names.key,
                journal=journal,
            ),
        )

    return wired
