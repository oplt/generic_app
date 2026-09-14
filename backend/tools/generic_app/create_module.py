"""Render and write module scaffolds from Jinja templates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from backend.tools.generic_app.naming import ModuleNames
from backend.tools.generic_app.wiring import (
    WiringError,
    wire_alembic_env,
    wire_api_router,
    wire_manifest_registry,
    wire_policy_catalog,
)
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


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


def build_context(names: ModuleNames, options: GeneratorOptions) -> dict[str, object]:
    dependencies = ["identity_access"]
    if options.storage:
        dependencies.append("storage")
    if options.crud and "projects" not in dependencies:
        # User-owned resources; identity is enough. projects optional.
        pass

    permissions: list[str] = []
    if options.permissions:
        permissions = [
            f"{names.permission_prefix}.read",
            f"{names.permission_prefix}.manage",
        ]

    return {
        "names": names,
        "options": options,
        "dependencies": tuple(dependencies),
        "permissions": tuple(permissions),
        "revision_id": _migration_revision_id(names.key),
        "celery_queue": names.key,
        "path_id": "{" + f"{names.entity}_id" + "}",
    }


def render_module(
    names: ModuleNames,
    options: GeneratorOptions,
) -> list[GeneratedFile]:
    context = build_context(names, options)
    generated: list[GeneratedFile] = []
    for relative_path, template_name in plan_module_files(names, options):
        # events.py requires application package — ensure package exists when
        # events without crud.
        generated.append(
            GeneratedFile(
                relative_path=relative_path,
                content=_render(template_name, context),
            )
        )

    # If events without crud, also emit application/__init__.py
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


def write_files(
    repo_root: Path,
    files: list[GeneratedFile],
    *,
    force: bool = False,
) -> tuple[list[str], list[str]]:
    written: list[str] = []
    skipped: list[str] = []
    for item in files:
        target = repo_root / item.relative_path
        if target.exists() and not force:
            skipped.append(item.relative_path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
        written.append(item.relative_path)
    return written, skipped


def apply_wiring(repo_root: Path, names: ModuleNames, options: GeneratorOptions) -> list[str]:
    wired: list[str] = []
    registry = repo_root / "backend/modules/manifests/registry.py"
    router = repo_root / "backend/api/router.py"
    if wire_manifest_registry(registry, names):
        wired.append(str(registry.relative_to(repo_root)))
    if wire_api_router(router, names):
        wired.append(str(router.relative_to(repo_root)))
    if options.crud:
        env_path = repo_root / "backend/alembic/env.py"
        if wire_alembic_env(env_path, names):
            wired.append(str(env_path.relative_to(repo_root)))
    if options.permissions:
        catalog = repo_root / "backend/modules/policy/catalog.py"
        if wire_policy_catalog(catalog, names):
            wired.append(str(catalog.relative_to(repo_root)))
    return wired


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

    files = render_module(names, options)
    result = GenerationResult(module_key=names.key, files=files)

    if dry_run:
        result.notes.append("Dry run — no files written and no wiring applied.")
        return result

    _written, skipped = write_files(root, files, force=options.force)
    result.skipped = skipped

    if options.wire:
        try:
            result.wired = apply_wiring(root, names, options)
        except WiringError as exc:
            result.notes.append(f"Wiring incomplete: {exc}")
    else:
        result.notes.append("Skipped registry/router wiring (--no-wire).")

    result.notes.append(
        "Review generated manifest registration, run migrations if --crud, "
        "and add nav/routes only if needed."
    )
    if options.permissions and options.wire:
        result.notes.append(
            "Permission constants were appended to policy catalog; seed/migrate "
            "roles as needed for new keys."
        )
    elif options.permissions:
        result.notes.append(
            f"Add {names.permission_prefix}.read / "
            f"{names.permission_prefix}.manage to policy catalog when wiring."
        )
    if options.celery:
        result.notes.append(
            f"Register Celery task module and include queue '{names.key}' in worker -Q."
        )
    if options.frontend:
        result.notes.append(
            "Wire the generated feature view into the app router / navigation manually."
        )
    return result
