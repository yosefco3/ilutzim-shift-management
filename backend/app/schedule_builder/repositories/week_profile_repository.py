"""
WeekProfileRepository — data access for week ↔ profile assignments (part B).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import BaseRepository
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment


class WeekProfileRepository(BaseRepository[WeekProfileAssignment]):
    """Data-access operations for WeekProfileAssignment entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WeekProfileAssignment)

    async def get_by_week(self, week_id: uuid.UUID) -> WeekProfileAssignment | None:
        """Return the assignment for a week, or None if it uses the default."""
        result = await self.session.execute(
            select(self.model_class).where(WeekProfileAssignment.week_id == week_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, week_id: uuid.UUID, profile_id: uuid.UUID
    ) -> WeekProfileAssignment:
        """Set the week's profile, replacing any existing assignment."""
        existing = await self.get_by_week(week_id)
        if existing is not None:
            existing.profile_id = profile_id
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.save(
            WeekProfileAssignment(week_id=week_id, profile_id=profile_id)
        )
