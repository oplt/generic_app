import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from backend.core.pagination import (
    decode_cursor,
    encode_cursor,
    paginate_cursor_scalars,
    paginated_response,
)
from backend.modules.notifications.models import Notification


class CursorPaginationTest(unittest.IsolatedAsyncioTestCase):
    def test_cursor_round_trip_is_opaque_and_stable(self):
        value = datetime(2026, 7, 11, 12, 30, tzinfo=UTC)
        cursor = encode_cursor(value=value, row_id="row-1")
        self.assertEqual(decode_cursor(cursor), (value, "row-1"))

    def test_invalid_cursor_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_cursor("not-a-valid-cursor")

    async def test_cursor_page_uses_probe_row_not_count(self):
        db = MagicMock()
        db.scalar = AsyncMock()
        result = MagicMock()
        created_at = datetime(2026, 7, 11, 12, 30, tzinfo=UTC)
        result.scalars.return_value.all.return_value = [
            SimpleNamespace(created_at=created_at, id="row-1"),
            SimpleNamespace(created_at=created_at, id="row-2"),
        ]
        db.execute = AsyncMock(return_value=result)

        rows, next_cursor, has_more = await paginate_cursor_scalars(
            db,
            select(Notification),
            limit=1,
            cursor=None,
            sort_column=Notification.created_at,
            id_column=Notification.id,
        )

        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(next_cursor)
        self.assertTrue(has_more)
        db.scalar.assert_not_awaited()

    def test_cursor_response_exposes_has_more_without_total(self):
        response = paginated_response(
            [], total=None, limit=50, offset=0, next_cursor="next", has_more=True
        )
        self.assertIsNone(response.total)
        self.assertTrue(response.has_more)
