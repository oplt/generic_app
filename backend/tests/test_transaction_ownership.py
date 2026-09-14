from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.api.deps.db import get_db


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def test_api_dependency_rolls_back_failed_request() -> None:
    session = SimpleNamespace(rollback=AsyncMock())

    async def exercise() -> None:
        with patch("backend.api.deps.db.SessionLocal", return_value=_SessionContext(session)):
            dependency = get_db()
            assert await anext(dependency) is session
            with pytest.raises(RuntimeError, match="request failed"):
                await dependency.athrow(RuntimeError("request failed"))

    asyncio.run(exercise())
    session.rollback.assert_awaited_once()


def test_repository_layers_do_not_own_transactions() -> None:
    repository_files = sorted(
        path
        for path in Path(__file__).parents[1].glob("modules/**/repository.py")
        if "/tests/" not in path.as_posix()
    )
    assert repository_files
    for path in repository_files:
        source = path.read_text(encoding="utf-8")
        assert ".commit(" not in source, path


def test_audited_admin_routes_keep_the_route_as_commit_owner() -> None:
    route_paths = (
        "modules/platform/config_routes.py",
        "modules/platform/feature_flag_routes.py",
        "modules/platform/email_template_routes.py",
        "modules/platform/billing_routes.py",
        "modules/settings/router.py",
    )
    for relative_path in route_paths:
        source = (Path(__file__).parents[1] / relative_path).read_text(encoding="utf-8")
        assert "commit=False" in source, relative_path
