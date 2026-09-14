import inspect
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import (
    Organization,
    OrganizationMembership,
    RefreshSession,
    User,
)


class IdentityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        value = result.scalar_one_or_none()
        if inspect.isawaitable(value):
            value = await value
        return value

    async def create_personal_organization(self, user: User) -> Organization:
        organization = Organization(name=(user.full_name or user.email).strip()[:255])
        self.db.add(organization)
        await self.db.flush()
        self.db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
            )
        )
        await self.db.flush()
        try:
            from backend.modules.policy.service import PolicyService

            await PolicyService(self.db).invalidate_user(user.id)
            await PolicyService(self.db).invalidate_organization(organization.id)
        except Exception:
            # Cache invalidation must not block signup org creation.
            pass
        return organization

    async def get_default_organization_id(self, user_id: str) -> str | None:
        result = await self.db.execute(
            select(OrganizationMembership.organization_id)
            .where(OrganizationMembership.user_id == user_id)
            .order_by(
                OrganizationMembership.created_at.asc(),
                OrganizationMembership.id.asc(),
            )
            .limit(1)
        )
        value = result.scalar_one_or_none()
        if inspect.isawaitable(value):
            value = await value
        return value

    async def user_belongs_to_organization(
        self, user_id: str, organization_id: str
    ) -> bool:
        result = await self.db.execute(
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
            )
            .limit(1)
        )
        value = result.scalar_one_or_none()
        if inspect.isawaitable(value):
            value = await value
        return value is not None

    async def create_user(
        self,
        email: str,
        password_hash: str,
        full_name: str | None,
        is_admin: bool = False,
        is_verified: bool = False,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            is_admin=is_admin,
            is_verified=is_verified,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def create_refresh_session(
        self, user_id: str, token_hash: str, expires_at: datetime
    ) -> RefreshSession:
        session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_refresh_session_by_hash(self, token_hash: str) -> RefreshSession | None:
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_session(self, session: RefreshSession) -> None:
        session.is_revoked = True
        await self.db.flush()

    async def rotate_refresh_session(self, session_id: str, token_hash: str) -> bool:
        """Revoke a refresh token exactly once for race-safe rotation."""
        result = await self.db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.id == session_id,
                RefreshSession.token_hash == token_hash,
                RefreshSession.is_revoked.is_(False),
                RefreshSession.expires_at > datetime.now(UTC),
            )
            .values(is_revoked=True)
        )
        await self.db.flush()
        return result.rowcount == 1

    async def revoke_all_refresh_sessions_for_user(self, user_id: str) -> None:
        sessions = await self.list_active_sessions(user_id, limit=None)
        for session in sessions:
            session.is_revoked = True
        await self.db.flush()

    async def list_active_sessions(
        self, user_id: str, *, limit: int | None = 50
    ) -> list[RefreshSession]:
        now = datetime.now(UTC)
        stmt = (
            select(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.is_revoked.is_(False),
                RefreshSession.expires_at > now,
            )
            .order_by(RefreshSession.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_session_by_id(self, session_id: str) -> RefreshSession | None:
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_active_session_by_id(self, session_id: str) -> RefreshSession | None:
        session = await self.get_session_by_id(session_id)
        if not session or session.is_revoked:
            return None
        if session.expires_at <= datetime.now(UTC):
            return None
        return session
