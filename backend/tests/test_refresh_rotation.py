import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.modules.identity_access.service import IdentityService


class RefreshRotationTest(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_rotation_rejects_replay_after_first_rotation(self) -> None:
        session = SimpleNamespace(
            id="session-1",
            user_id="user-1",
            is_revoked=False,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        user = SimpleNamespace(id="user-1", is_active=True, is_verified=True)
        repo = SimpleNamespace(
            get_refresh_session_by_hash=AsyncMock(return_value=session),
            get_user_by_id=AsyncMock(return_value=user),
            rotate_refresh_session=AsyncMock(side_effect=[True, False]),
            create_refresh_session=AsyncMock(return_value=SimpleNamespace(id="session-2")),
        )
        db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        service = IdentityService(db)  # type: ignore[arg-type]
        service.repo = repo

        with (
            patch(
                "backend.modules.identity_access.service.hash_refresh_token",
                side_effect=lambda token: f"hash:{token}",
            ),
            patch(
                "backend.modules.identity_access.service.generate_refresh_token",
                side_effect=["rotated-token", "replay-token"],
            ),
            patch(
                "backend.modules.identity_access.service.settings.REQUIRE_EMAIL_VERIFICATION",
                False,
            ),
        ):
            first = await service.refresh("original-token")
            self.assertEqual(first["session_id"], "session-2")
            with self.assertRaises(HTTPException) as context:
                await service.refresh("original-token")

        self.assertEqual(context.exception.status_code, 401)
        db.rollback.assert_awaited_once()
