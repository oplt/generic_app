from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.policy.deps import require_permission
from backend.modules.orders.api.schemas import (
    OrderCreate,
    OrderResponse,
    OrderUpdate,
)
from backend.modules.orders.application.service import OrdersService

router = APIRouter()


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("orders.read")),
):
    return await OrdersService(db).list_for_user(current_user.id)


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("orders.manage")),
):
    return await OrdersService(db).create(current_user.id, payload)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("orders.read")),
):
    return await OrdersService(db).get(current_user.id, order_id)


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    payload: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("orders.manage")),
):
    return await OrdersService(db).update(current_user.id, order_id, payload)


@router.delete("/{order_id}", status_code=204)
async def delete_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("orders.manage")),
):
    await OrdersService(db).delete(current_user.id, order_id)
