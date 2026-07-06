"""
User repository — data access for security guard users.
"""

import uuid

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """Data-access operations for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_phone(self, phone_number: str) -> User | None:
        """Find a user by phone number."""
        stmt = select(self.model_class).where(User.phone_number == phone_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: str) -> User | None:
        """Find a user by Telegram ID."""
        stmt = select(self.model_class).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_users(self) -> list[User]:
        """Return only active ORGANIC-team users, in a deterministic order.

        Reinforcement guards (מתגברים — ad-hoc external helpers on the actual
        board) are excluded here, in one place, so every by-guard consumer —
        the attendance comparison and payroll, Telegram broadcasts, constraint
        exports, both schedule read models — never sees them. Their placements
        still appear position-wise (the actual board and its Excel).
        """
        stmt = (
            select(self.model_class)
            .where(User.is_active.is_(True))
            .where(User.is_reinforcement.is_(False))
            .order_by(User.last_name, User.first_name, User.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
        """Return users matching the given ids, ordered by name."""
        if not user_ids:
            return []
        stmt = (
            select(self.model_class)
            .where(User.id.in_(user_ids))
            .order_by(User.last_name, User.first_name, User.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_users(self) -> list[User]:
        """Return all TEAM users (active and inactive) — the guards page.

        Reinforcements are managed from the actual board, not here.
        """
        stmt = (
            select(self.model_class)
            .where(User.is_reinforcement.is_(False))
            .order_by(User.is_active.desc(), User.last_name, User.first_name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def link_telegram_id_by_phone(self, phone_number: str, telegram_id: str) -> User:
        """Link a Telegram ID to a user identified by phone number.

        Raises ValueError if no user is found with the given phone number.
        """
        user = await self.get_by_phone(phone_number)
        if user is None:
            raise ValueError(f"No user found with phone number {phone_number}")
        user.telegram_id = telegram_id
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def link_telegram_id_by_user_id(self, user_id: uuid.UUID, telegram_id: str) -> User:
        """Link a Telegram ID to a user identified by user ID.

        Raises ValueError if no user is found with the given user ID.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError(f"No user found with id {user_id}")
        user.telegram_id = telegram_id
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def deactivate_user(self, user_id: uuid.UUID) -> User:
        """Set is_active=False on a user."""
        return await self.update(user_id, is_active=False)