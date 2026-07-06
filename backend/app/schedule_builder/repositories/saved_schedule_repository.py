"""
SavedScheduleRepository — data access for saved-schedule snapshots (part B).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import BaseRepository
from app.schedule_builder.models.saved_schedule import SavedSchedule


class SavedScheduleRepository(BaseRepository[SavedSchedule]):
    """Data-access operations for SavedSchedule entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SavedSchedule)

    async def get_by_week(self, week_id: uuid.UUID) -> SavedSchedule | None:
        """Return the snapshot for a week, or None if it was never saved."""
        stmt = select(self.model_class).where(SavedSchedule.week_id == week_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[SavedSchedule]:
        """Return all saved-schedule rows, most-recently-saved first.

        Used by the Weeks page to learn which weeks have a downloadable snapshot.
        """
        stmt = select(self.model_class).order_by(SavedSchedule.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self, week_id: uuid.UUID, profile_name: str | None, snapshot: dict
    ) -> SavedSchedule:
        """Create or overwrite the week's snapshot (one snapshot per week).

        On overwrite, ``updated_at`` bumps via the model's ``onupdate`` — that is
        the "last saved" time surfaced to the UI.
        """
        existing = await self.get_by_week(week_id)
        if existing is not None:
            existing.profile_name = profile_name
            existing.snapshot = snapshot
            await self.session.flush()
            # Reload server-generated ``updated_at`` (onupdate=now) inside the
            # async context; else accessing it later raises MissingGreenlet.
            await self.session.refresh(existing)
            return existing
        instance = SavedSchedule(
            week_id=week_id, profile_name=profile_name, snapshot=snapshot
        )
        self.session.add(instance)
        await self.session.flush()
        # Reload server-generated timestamps inside the async context.
        await self.session.refresh(instance)
        return instance
