from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    paginated_response,
    pagination_params,
)
from backend.modules.identity_access.models import User
from backend.modules.notifications.repository import NotificationsRepository
from backend.modules.notifications.schemas import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationResponse,
)
from backend.observability.workflow import observe_async_workflow

router = APIRouter()


@router.get("/unread-count")
@observe_async_workflow("notifications", "unread_count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"count": await NotificationsRepository(db).unread_count(current_user.id)}


@router.get("", response_model=PaginatedResponse[NotificationResponse])
@observe_async_workflow("notifications", "list")
async def list_notifications(
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    next_cursor = None
    has_more = False
    if getattr(pagination, "cursor", None):
        items, next_cursor, has_more = await repo.list_for_user_cursor(
            current_user.id, limit=pagination.limit, cursor=pagination.cursor
        )
        total = None
    else:
        items, total = await repo.list_for_user(
            current_user.id, limit=pagination.limit, offset=pagination.offset
        )
    return paginated_response(
        [
            NotificationResponse(
                id=n.id,
                type=n.type,
                title=n.title,
                body=n.body,
                is_read=n.is_read,
                created_at=n.created_at,
            )
            for n in items
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.patch("/{notification_id}/read", status_code=204)
@observe_async_workflow("notifications", "mark_read")
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    n = await repo.get_by_id(notification_id)
    if not n or n.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    await repo.mark_read(n)
    await db.commit()


@router.patch("/read-all", status_code=204)
@observe_async_workflow("notifications", "mark_all_read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    await repo.mark_all_read(current_user.id)
    await db.commit()


@router.get("/preferences", response_model=NotificationPreferenceResponse)
@observe_async_workflow("notifications", "get_preferences")
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    prefs = await repo.get_or_create_preferences(current_user.id)
    await db.commit()
    return NotificationPreferenceResponse(
        email_enabled=prefs.email_enabled,
        push_enabled=prefs.push_enabled,
        marketing_enabled=prefs.marketing_enabled,
    )


@router.put("/preferences", response_model=NotificationPreferenceResponse)
@observe_async_workflow("notifications", "update_preferences")
async def update_preferences(
    payload: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    prefs = await repo.get_or_create_preferences(current_user.id)
    if payload.email_enabled is not None:
        prefs.email_enabled = payload.email_enabled
    if payload.push_enabled is not None:
        prefs.push_enabled = payload.push_enabled
    if payload.marketing_enabled is not None:
        prefs.marketing_enabled = payload.marketing_enabled
    await db.commit()
    return NotificationPreferenceResponse(
        email_enabled=prefs.email_enabled,
        push_enabled=prefs.push_enabled,
        marketing_enabled=prefs.marketing_enabled,
    )
