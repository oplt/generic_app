"""Render and write module scaffolds from Jinja templates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from backend.tools.generic_app.alembic_resolve import (
    AlembicResolveError,
    resolve_alembic_down_revision,
)
from backend.tools.generic_app.journal import MutationJournal
from backend.tools.generic_app.naming import ModuleNames
from backend.tools.generic_app.wiring import WiringError, apply_all_wiring
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

Enablement = Literal["optional", "core", "profile"]


@dataclass(frozen=True, slots=True)
class GeneratorOptions:
    crud: bool = False
    frontend: bool = False
    celery: bool = False
    permissions: bool = False
    events: bool = False
    storage: bool = False
    wire: bool = True
    force: bool = False
    enablement: Enablement = "optional"
    profile: str | None = None


@dataclass
class GeneratedFile:
    relative_path: str
    content: str


@dataclass
class GenerationResult:
    module_key: str
    files: list[GeneratedFile] = field(default_factory=list)
    wired: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rolled_back: bool = False


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _render(template_name: str, context: dict[str, object]) -> str:
    return _env().get_template(template_name).render(**context)


def _migration_revision_id(module_key: str) -> str:
    digest = hashlib.sha1(f"generic-app-module:{module_key}".encode()).hexdigest()
    return f"g{digest[:11]}"


def plan_module_files(
    names: ModuleNames,
    options: GeneratorOptions,
) -> list[tuple[str, str]]:
    """Return (relative_path, template_name) pairs for the selected options."""

    files: list[tuple[str, str]] = [
        (f"backend/modules/{names.key}/__init__.py", "backend/__init__.py.j2"),
        (f"backend/modules/{names.key}/manifest.py", "backend/manifest.py.j2"),
        (f"backend/modules/{names.key}/api/__init__.py", "backend/api/__init__.py.j2"),
        (f"backend/modules/{names.key}/api/router.py", "backend/api/router.py.j2"),
        (
            f"backend/modules/{names.key}/tests/__init__.py",
            "backend/tests/__init__.py.j2",
        ),
        (
            f"backend/modules/{names.key}/tests/test_manifest.py",
            "backend/tests/test_manifest.py.j2",
        ),
    ]

    if options.crud:
        files.extend(
            [
                (
                    f"backend/modules/{names.key}/api/schemas.py",
                    "backend/api/schemas.py.j2",
                ),
                (
                    f"backend/modules/{names.key}/application/__init__.py",
                    "backend/application/__init__.py.j2",
                ),
                (
                    f"backend/modules/{names.key}/application/service.py",
                    "backend/application/service.py.j2",
                ),
                (
                    f"backend/modules/{names.key}/infrastructure/__init__.py",
                    "backend/infrastructure/__init__.py.j2",
                ),
                (
                    f"backend/modules/{names.key}/infrastructure/models.py",
                    "backend/infrastructure/models.py.j2",
                ),
                (
                    f"backend/modules/{names.key}/infrastructure/repository.py",
                    "backend/infrastructure/repository.py.j2",
                ),
                (
                    f"backend/modules/{names.key}/tests/test_service.py",
                    "backend/tests/test_service.py.j2",
                ),
                (
                    f"backend/alembic/versions/{_migration_revision_id(names.key)}"
                    f"_add_{names.key}_table.py",
                    "migration/alembic_revision.py.j2",
                ),
            ]
        )

    if options.celery:
        files.append(
            (f"backend/modules/{names.key}/workers.py", "backend/workers.py.j2")
        )

    if options.events:
        files.append(
            (
                f"backend/modules/{names.key}/application/events.py",
                "backend/application/events.py.j2",
            )
        )

    if options.frontend:
        base = f"frontend/src/features/{names.key}"
        files.extend(
            [
                (f"{base}/api.ts", "frontend/api.ts.j2"),
                (f"{base}/types.ts", "frontend/types.ts.j2"),
                (f"{base}/hooks/use{names.pascal}List.ts", "frontend/hooks/useList.ts.j2"),
                (
                    f"{base}/views/{names.pascal}ListView.tsx",
                    "frontend/views/ListView.tsx.j2",
                ),
            ]
        )

    return files


def build_context(
    names: ModuleNames,
    options: GeneratorOptions,
    *,
    down_revision: str | None = None,
) -> dict[str, object]:
    dependencies = ["identity_access"]
    if options.storage:
        dependencies.append("storage")

    permissions: list[str] = []
    if options.permissions:
        permissions = [
            f"{names.permission_prefix}.read",
            f"{names.permission_prefix}.manage",
        ]

    always_enabled = options.enablement == "core"
    optional = options.enablement == "optional"

    return {
        "names": names,
        "options": options,
        "dependencies": tuple(dependencies),
        "permissions": tuple(permissions),
        "revision_id": _migration_revision_id(names.key),
        "down_revision": down_revision,
        "celery_queue": names.key,
        "path_id": "{" + f"{names.entity}_id" + "}",
        "always_enabled": always_enabled,
        "optional": optional,
        "page_key": f"{names.key}.list",
        "nav_path": f"/{names.key}",
    }


def render_module(
    names: ModuleNames,
    options: GeneratorOptions,
    *,
    down_revision: str | None = None,
) -> list[GeneratedFile]:
    context = build_context(names, options, down_revision=down_revision)
    generated: list[GeneratedFile] = []
    for relative_path, template_name in plan_module_files(names, options):
        generated.append(
            GeneratedFile(
                relative_path=relative_path,
                content=_render(template_name, context),
            )
        )

    if options.events and not options.crud:
        init_path = f"backend/modules/{names.key}/application/__init__.py"
        if not any(item.relative_path == init_path for item in generated):
            generated.insert(
                -1 if generated else 0,
                GeneratedFile(
                    relative_path=init_path,
                    content=_render("backend/application/__init__.py.j2", context),
                ),
            )
    return generated


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "backend" / "modules").is_dir() and (
            candidate / "frontend" / "src"
        ).is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate repository root (expected backend/modules and frontend/src)."
    )


def create_module(
    module_key: str,
    *,
    options: GeneratorOptions,
    repo_root: Path | None = None,
    entity: str | None = None,
    dry_run: bool = False,
) -> GenerationResult:
    names = ModuleNames.from_key(module_key, entity=entity)
    root = repo_root or find_repo_root()
    module_dir = root / "backend" / "modules" / names.key
    if module_dir.exists() and not options.force and not dry_run:
        raise FileExistsError(
            f"Module directory already exists: {module_dir}. Use --force to overwrite files."
        )

    if options.enablement == "profile":
        if not options.profile:
            raise ValueError("--profile enablement requires a profile key")
        from backend.modules.platform.profiles import CAPABILITY_PROFILES

        if options.profile not in CAPABILITY_PROFILES:
            known = ", ".join(sorted(CAPABILITY_PROFILES))
            raise ValueError(
                f"Unknown capability profile {options.profile!r}. Known: {known}"
            )

    down_revision: str | None = None
    if options.crud:
        try:
            down_revision = resolve_alembic_down_revision(root)
        except AlembicResolveError as exc:
            raise ValueError(str(exc)) from exc

    files = render_module(names, options, down_revision=down_revision)
    result = GenerationResult(module_key=names.key, files=files)

    if dry_run:
        result.notes.append("Dry run — no files written and no wiring applied.")
        if options.crud:
            result.notes.append(f"Resolved Alembic down_revision={down_revision!r}")
        return result

    journal = MutationJournal()
    try:
        for item in files:
            target = root / item.relative_path
            if target.exists() and not options.force:
                result.skipped.append(item.relative_path)
                continue
            journal.write_text(target, item.content)

        if options.wire:
            result.wired = apply_all_wiring(
                root,
                names,
                crud=options.crud,
                permissions=options.permissions,
                celery=options.celery,
                frontend=options.frontend,
                profile=options.profile if options.enablement == "profile" else None,
                journal=journal,
            )
        else:
            result.notes.append("Skipped registry/router wiring (--no-wire).")
    except (WiringError, OSError, ValueError) as exc:
        journal.rollback()
        result.rolled_back = True
        raise RuntimeError(
            f"Module generation failed and was rolled back: {exc}"
        ) from exc

    if options.enablement == "optional":
        result.notes.append(
            "Manifest is optional (pack toggle); enable via module pack / overrides."
        )
    elif options.enablement == "core":
        result.notes.append("Manifest is always_enabled core.")
    elif options.profile:
        result.notes.append(
            f"Manifest selected for capability profile {options.profile!r}."
        )

    if options.permissions and options.wire:
        result.notes.append(
            "Permission constants were appended to policy catalog; seed/migrate "
            "roles as needed for new keys."
        )
    if options.crud:
        result.notes.append(
            f"Alembic revision parent resolved to {down_revision!r}; run upgrade when ready."
        )
    return result
