"""
PositionRepository — data access for positions (part B).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import BaseRepository
from app.schedule_builder.models.position import Position


class PositionRepository(BaseRepository[Position]):
    """Data-access operations for Position entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Position)

    async def get_by_profile(self, profile_id: uuid.UUID) -> list[Position]:
        """Return a profile's positions, ordered by display_order."""
        stmt = (
            select(self.model_class)
            .where(Position.profile_id == profile_id)
            .order_by(Position.display_order.asc(), Position.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_display_order(
        self, position_id: uuid.UUID, order: int
    ) -> None:
        """Set a single position's display_order (used by bulk reorder)."""
        await self.update(position_id, display_order=order)

    async def max_display_order_in_profile(self, profile_id: uuid.UUID) -> int:
        """Return the highest display_order within a profile (0 if none)."""
        result = await self.session.execute(
            select(func.coalesce(func.max(Position.display_order), 0)).where(
                Position.profile_id == profile_id
            )
        )
        return result.scalar() or 0
