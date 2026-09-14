from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orders.infrastructure.models import Order


class OrdersRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_user(self, user_id: str) -> list[Order]:
        result = await self.db.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, order_id: str) -> Order | None:
        return await self.db.get(Order, order_id)

    async def create(
        self,
        *,
        user_id: str,
        title: str,
        description: str | None,
    ) -> Order:
        item = Order(
            user_id=user_id,
            title=title,
            description=description,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def delete(self, item: Order) -> None:
        await self.db.delete(item)
