from sqlalchemy.ext.asyncio import AsyncSession
from backend.modules.identity_access.models import User


class UsersRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_profile(self, user: User, full_name: str | None) -> User:
        user.full_name = full_name
        await self.db.flush()
        return user