"""CLI entrypoint: ``generic-app`` / ``python -m backend.tools.generic_app``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.tools.generic_app import __version__
from backend.tools.generic_app.create_module import (
    GeneratorOptions,
    create_module,
    find_repo_root,
)
from backend.tools.generic_app.naming import validate_module_key


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generic-app",
        description="Scaffold application modules for the generic_app monorepo.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser(
        "create-module",
        help="Generate a backend (and optional frontend) module scaffold.",
    )
    create.add_argument("name", help="Module key (lowercase snake_case), e.g. orders")
    create.add_argument(
        "--entity",
        default=None,
        help="Singular entity key (default: singularized module name)",
    )
    create.add_argument("--crud", action="store_true", help="Generate CRUD model/service/routes")
    create.add_argument("--frontend", action="store_true", help="Generate React feature scaffold")
    create.add_argument("--celery", action="store_true", help="Generate Celery worker stub + queue")
    create.add_argument(
        "--permissions",
        action="store_true",
        help="Wire policy permission keys and require_permission on routes",
    )
    create.add_argument(
        "--events",
        action="store_true",
        help="Generate outbox-ready event helper stubs",
    )
    create.add_argument(
        "--storage",
        action="store_true",
        help="Declare storage dependency on the module manifest",
    )
    create.add_argument(
        "--no-wire",
        action="store_true",
        help="Do not patch registry/router/alembic/policy catalog",
    )
    create.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated files",
    )
    create.add_argument(
        "--dry-run",
        action="store_true",
        help="Render plan only; write nothing",
    )
    create.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (default: discover from cwd)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "create-module":
        try:
            validate_module_key(args.name)
            if args.entity:
                validate_module_key(args.entity)
        except ValueError as exc:
            parser.error(str(exc))

        if args.events and not args.crud:
            # events helper imports the model; require crud for a coherent stub.
            parser.error("--events requires --crud (event helpers reference the model)")
        if args.frontend and not args.crud:
            parser.error("--frontend requires --crud (list/detail API contract)")

        options = GeneratorOptions(
            crud=args.crud,
            frontend=args.frontend,
            celery=args.celery,
            permissions=args.permissions,
            events=args.events,
            storage=args.storage,
            wire=not args.no_wire,
            force=args.force,
        )
        try:
            root = args.root or find_repo_root()
            result = create_module(
                args.name,
                options=options,
                repo_root=root,
                entity=args.entity,
                dry_run=args.dry_run,
            )
        except (FileExistsError, FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(f"Module `{result.module_key}` — {len(result.files)} file(s) planned")
        for item in result.files:
            print(f"  {item.relative_path}")
        if result.wired:
            print("Wired:")
            for path in result.wired:
                print(f"  {path}")
        if result.skipped:
            print("Skipped (exists):")
            for path in result.skipped:
                print(f"  {path}")
        for note in result.notes:
            print(f"note: {note}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
