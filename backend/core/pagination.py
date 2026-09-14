from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Generic, TypeVar

from fastapi import HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Offset responses include total; cursor responses use has_more instead."""

    items: list[T]
    total: int | None = None
    limit: int
    offset: int
    next_cursor: str | None = None
    has_more: bool = False


class PaginationParams(BaseModel):
    limit: int
    offset: int
    cursor: str | None = None


def pagination_params(
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
) -> PaginationParams:
    if cursor:
        try:
            decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid pagination cursor") from exc
    return PaginationParams(limit=limit, offset=offset, cursor=cursor)


def encode_cursor(*, value: datetime, row_id: str) -> str:
    payload = f"{value.isoformat()}\0{row_id}".encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    padding = "=" * (-len(cursor) % 4)
    try:
        raw_value, row_id = base64.urlsafe_b64decode(cursor + padding).decode().split("\0", 1)
        return datetime.fromisoformat(raw_value), row_id
    except (ValueError, UnicodeDecodeError, base64.binascii.Error) as exc:
        raise ValueError("Invalid pagination cursor") from exc


def paginated_response(  # noqa: UP047
    items: list[T],
    *,
    total: int | None,
    limit: int,
    offset: int,
    next_cursor: str | None = None,
    has_more: bool | None = None,
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        next_cursor=next_cursor,
        has_more=next_cursor is not None if has_more is None else has_more,
    )


async def paginate_scalars(
    db: AsyncSession,
    stmt: Select,
    *,
    limit: int,
    offset: int,
) -> tuple[list, int]:
    """Execute a paginated scalar select. stmt must not already apply offset/limit."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(await db.scalar(count_stmt) or 0)
    result = await db.execute(stmt.offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def paginate_scalars_preview(
    db: AsyncSession,
    stmt: Select,
    *,
    limit: int,
) -> tuple[list, bool]:
    """Fetch one extra row for high-volume previews without running COUNT(*)."""
    result = await db.execute(stmt.limit(limit + 1))
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    return rows[:limit], has_more


async def paginate_cursor_scalars(
    db: AsyncSession,
    stmt: Select,
    *,
    limit: int,
    cursor: str | None,
    sort_column: Any,
    id_column: Any,
) -> tuple[list, str | None, bool]:
    """Keyset paginate without a count query; return next cursor and has-more."""
    if cursor:
        cursor_value, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            (sort_column < cursor_value) | ((sort_column == cursor_value) & (id_column < cursor_id))
        )
    stmt = stmt.order_by(sort_column.desc(), id_column.desc())
    result = await db.execute(stmt.limit(limit + 1))
    rows = list(result.scalars().all())
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = encode_cursor(
            value=getattr(last, sort_column.key), row_id=getattr(last, id_column.key)
        )
    return rows, next_cursor, has_next


async def paginate_cursor_rows(
    db: AsyncSession,
    stmt: Select,
    *,
    limit: int,
    cursor: str | None,
    sort_column: Any,
    id_column: Any,
) -> tuple[list, str | None, bool]:
    """Keyset paginate row tuples without a count query."""
    if cursor:
        cursor_value, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            (sort_column < cursor_value) | ((sort_column == cursor_value) & (id_column < cursor_id))
        )
    stmt = stmt.order_by(sort_column.desc(), id_column.desc())
    result = await db.execute(stmt.limit(limit + 1))
    rows = list(result.all())
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        last = rows[-1][0]
        next_cursor = encode_cursor(
            value=getattr(last, sort_column.key), row_id=getattr(last, id_column.key)
        )
    return rows, next_cursor, has_next
