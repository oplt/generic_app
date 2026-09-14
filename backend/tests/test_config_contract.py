"""Config contracts: Settings ↔ .env.example ↔ OpenAPI export payload.

Prevents recurrence of OpenAPI-export failures where required Settings fields
were missing from the deterministic export environment.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.core.openapi_export import (
    OPENAPI_EXPORT_ENV,
    openapi_export_settings_kwargs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"
FRONTEND_ENV_EXAMPLE = REPO_ROOT / "frontend" / ".env.example"
INFRA_ENV_EXAMPLE = REPO_ROOT / "infra" / ".env.example"


def _parse_dotenv_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def _required_settings_fields() -> set[str]:
    return {
        name
        for name, field in Settings.model_fields.items()
        if field.is_required()
    }


def _settings_field_names() -> set[str]:
    return set(Settings.model_fields)


def test_required_settings_appear_in_backend_env_example() -> None:
    example_keys = _parse_dotenv_keys(BACKEND_ENV_EXAMPLE)
    missing = sorted(_required_settings_fields() - example_keys)
    assert missing == [], (
        "Required Settings fields missing from backend/.env.example: "
        f"{missing}. Add them so local/CI setup stays constructible."
    )


def test_all_settings_fields_documented_in_backend_env_example() -> None:
    """Every Settings field should be discoverable in the backend example.

    Optional / secret fields may be blank, but must be listed so operators
    know the knobs exist. CAPABILITY_PROFILE may be commented; still count
    the key if present as a comment assignment marker.
    """

    text = BACKEND_ENV_EXAMPLE.read_text(encoding="utf-8")
    example_keys = _parse_dotenv_keys(BACKEND_ENV_EXAMPLE)
    # Allow documenting optional aliases via commented assignment lines.
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#") and "=" in stripped:
            candidate = stripped.lstrip("#").strip().split("=", 1)[0].strip()
            if candidate.isidentifier() and candidate.isupper():
                example_keys.add(candidate)

    missing = sorted(_settings_field_names() - example_keys)
    assert missing == [], (
        "Settings fields not listed in backend/.env.example (active or "
        f"commented): {missing}"
    )


def test_backend_env_example_keys_are_known_settings() -> None:
    unknown = sorted(_parse_dotenv_keys(BACKEND_ENV_EXAMPLE) - _settings_field_names())
    assert unknown == [], (
        "backend/.env.example contains keys unknown to Settings "
        f"(stale/outdated): {unknown}"
    )


def test_openapi_export_env_covers_required_settings() -> None:
    missing = sorted(_required_settings_fields() - set(OPENAPI_EXPORT_ENV))
    assert missing == [], (
        "OPENAPI_EXPORT_ENV is missing required Settings keys: "
        f"{missing}. OpenAPI export will fail in clean CI without them."
    )


def test_openapi_export_env_keys_are_known_settings() -> None:
    unknown = sorted(set(OPENAPI_EXPORT_ENV) - _settings_field_names())
    assert unknown == [], f"OPENAPI_EXPORT_ENV has unknown Settings keys: {unknown}"


def test_openapi_export_kwargs_match_env_payload() -> None:
    env_keys = set(OPENAPI_EXPORT_ENV)
    kwargs_keys = set(openapi_export_settings_kwargs())
    assert env_keys == kwargs_keys, (
        "OPENAPI_EXPORT_ENV and openapi_export_settings_kwargs() drifted: "
        f"env_only={sorted(env_keys - kwargs_keys)} "
        f"kwargs_only={sorted(kwargs_keys - env_keys)}"
    )


def test_openapi_export_kwargs_construct_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in OPENAPI_EXPORT_ENV:
        monkeypatch.delenv(key, raising=False)
    config = Settings.for_openapi_export()
    for key in _required_settings_fields():
        assert getattr(config, key) not in (None, ""), f"{key} empty on export settings"


def test_openapi_export_module_does_not_import_settings_at_load() -> None:
    """Regression: openapi_export must stay importable before Settings loads."""

    source = (REPO_ROOT / "backend" / "core" / "openapi_export.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
            "backend.core.config"
        ):
            imported.add(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("backend.core.config"):
                    imported.add(alias.name)
    assert not imported, (
        "backend.core.openapi_export must not import Settings at module load "
        f"(found {imported}); keep export env self-contained."
    )


def test_frontend_env_example_documents_vite_api_base() -> None:
    keys = _parse_dotenv_keys(FRONTEND_ENV_EXAMPLE)
    assert "VITE_API_BASE" in keys


def test_infra_env_example_documents_compose_secrets() -> None:
    keys = _parse_dotenv_keys(INFRA_ENV_EXAMPLE)
    expected = {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
    }
    assert expected <= keys, f"infra/.env.example missing {sorted(expected - keys)}"
