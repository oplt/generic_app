"""Resolve Alembic ``down_revision`` from the repository's current heads."""

from __future__ import annotations

from pathlib import Path


class AlembicResolveError(RuntimeError):
    """Raised when Alembic head topology is ambiguous or unreadable."""


def resolve_alembic_down_revision(repo_root: Path) -> str | None:
    """Return the single Alembic head revision id, or ``None`` if bootstrapping.

    * one head → that revision
    * zero heads → ``None`` (first migration)
    * multiple heads → fail clearly (do not guess)
    """

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError as exc:  # pragma: no cover
        raise AlembicResolveError(
            "alembic is required to resolve migration parents"
        ) from exc

    ini_path = repo_root / "backend" / "alembic.ini"
    if not ini_path.is_file():
        raise AlembicResolveError(f"Missing Alembic config: {ini_path}")

    config = Config(str(ini_path))
    # ScriptDirectory resolves relative to cwd; pin script location explicitly.
    versions = repo_root / "backend" / "alembic" / "versions"
    config.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    if not versions.is_dir():
        raise AlembicResolveError(f"Missing Alembic versions directory: {versions}")

    script = ScriptDirectory.from_config(config)
    heads = list(script.get_heads())
    if len(heads) == 1:
        return heads[0]
    if len(heads) == 0:
        return None
    raise AlembicResolveError(
        "Multiple Alembic heads detected; refuse to guess a parent revision: "
        + ", ".join(sorted(heads))
    )
