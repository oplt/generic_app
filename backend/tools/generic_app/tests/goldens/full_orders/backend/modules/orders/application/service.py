from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orders.api.schemas import (
    OrderCreate,
    OrderResponse,
    OrderUpdate,
)
from backend.modules.orders.infrastructure.models import Order
from backend.modules.orders.infrastructure.repository import OrdersRepository
from backend.modules.orders.application.events import emit_order_created


class OrdersService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrdersRepository(db)

    async def list_for_user(self, user_id: str) -> list[OrderResponse]:
        items = await self.repo.list_for_user(user_id)
        return [self._to_response(item) for item in items]

    async def get(self, user_id: str, order_id: str) -> OrderResponse:
        item = await self._get_owned(user_id, order_id)
        return self._to_response(item)

    async def create(
        self, user_id: str, payload: OrderCreate
    ) -> OrderResponse:
        item = await self.repo.create(
            user_id=user_id,
            title=payload.title,
            description=payload.description,
        )
        await self.db.commit()
        await self.db.refresh(item)
        await emit_order_created(self.db, item)
        return self._to_response(item)

    async def update(
        self,
        user_id: str,
        order_id: str,
        payload: OrderUpdate,
    ) -> OrderResponse:
        item = await self._get_owned(user_id, order_id)
        if payload.title is not None:
            item.title = payload.title
        if payload.description is not None:
            item.description = payload.description
        await self.db.commit()
        await self.db.refresh(item)
        return self._to_response(item)

    async def delete(self, user_id: str, order_id: str) -> None:
        item = await self._get_owned(user_id, order_id)
        await self.repo.delete(item)
        await self.db.commit()

    async def _get_owned(self, user_id: str, order_id: str) -> Order:
        item = await self.repo.get_by_id(order_id)
        if item is None or item.user_id != user_id:
            raise HTTPException(status_code=404, detail="Order not found")
        return item

    @staticmethod
    def _to_response(item: Order) -> OrderResponse:
        return OrderResponse(
            id=item.id,
            title=item.title,
            description=item.description,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
