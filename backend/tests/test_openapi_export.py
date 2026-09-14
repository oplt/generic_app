"""OpenAPI export must succeed from a clean CI-like environment."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.core.openapi_export import OPENAPI_EXPORT_ENV, install_openapi_export_env

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_settings_for_openapi_export_constructs_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in OPENAPI_EXPORT_ENV:
        monkeypatch.delenv(key, raising=False)

    config = Settings.for_openapi_export()

    assert config.JWT_ALGORITHM == "HS256"
    assert config.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert config.REFRESH_TOKEN_EXPIRE_DAYS == 7
    assert config.STORAGE_AUTO_CREATE_BUCKET is False
    assert config.capability_profile == "full_platform"


def test_openapi_export_succeeds_from_clean_ci_like_env(tmp_path: Path) -> None:
    """Subprocess with no app secrets proves exporter is self-contained."""

    output = tmp_path / "openapi.json"
    clean_env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", str(tmp_path)),
        "PYTHONPATH": str(REPO_ROOT),
        "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    # Intentionally omit DATABASE_URL / JWT_* / Redis / storage — exporter installs them.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.scripts.export_openapi",
            "--output",
            str(output),
        ],
        cwd=str(REPO_ROOT),
        env=clean_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert output.is_file()
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(schema.get("paths"), dict)
    assert len(schema["paths"]) > 0
    assert "openapi" in schema


def test_install_openapi_export_env_covers_required_settings_keys() -> None:
    required = {
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET",
        "JWT_ALGORITHM",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "REFRESH_TOKEN_EXPIRE_DAYS",
    }
    assert required <= set(OPENAPI_EXPORT_ENV)
    install_openapi_export_env(force=True)
    for key in required:
        assert os.environ.get(key)
