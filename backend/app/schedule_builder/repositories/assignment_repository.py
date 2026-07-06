"""
AssignmentRepository — data access for schedule assignments (part B, task 05).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.repositories.base_repository import BaseRepository
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment


class AssignmentRepository(BaseRepository[ScheduleAssignment]):
    """Data-access operations for ScheduleAssignment entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ScheduleAssignment)

    async def list_for_week(self, week_id: uuid.UUID) -> list[ScheduleAssignment]:
        """Return every assignment for a week (eager guard) to overlay on the board."""
        stmt = (
            select(self.model_class)
            .where(ScheduleAssignment.week_id == week_id)
            .options(selectinload(ScheduleAssignment.user))
            .order_by(
                ScheduleAssignment.position_id,
                ScheduleAssignment.day_index,
                ScheduleAssignment.created_at,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_impact_for_profile(
        self, profile_id: uuid.UUID
    ) -> tuple[int, int]:
        """Return ``(weeks, assignments)`` that would be wiped if this profile is
        deleted. Assignments sit on the profile's positions, so deleting the
        profile cascades them away (profile → positions → assignments). ``weeks``
        counts the distinct weeks that would lose part of their schedule."""
        stmt = (
            select(
                func.count(func.distinct(ScheduleAssignment.week_id)),
                func.count(ScheduleAssignment.id),
            )
            .join(Position, ScheduleAssignment.position_id == Position.id)
            .where(Position.profile_id == profile_id)
        )
        weeks, assignments = (await self.session.execute(stmt)).one()
        return int(weeks or 0), int(assignments or 0)

    async def get_with_user(
        self, assignment_id: uuid.UUID
    ) -> ScheduleAssignment | None:
        """Return one assignment with its guard eager-loaded (for the response)."""
        stmt = (
            select(self.model_class)
            .where(ScheduleAssignment.id == assignment_id)
            .options(selectinload(ScheduleAssignment.user))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_in_cell(
        self,
        week_id: uuid.UUID,
        position_id: uuid.UUID,
        day_index: int,
    ) -> list[ScheduleAssignment]:
        """All assignments in a cell (week×position×day), oldest first.

        Used to enforce the two-guard cap and to order the tiling segments —
        the first-created assignment is "guard A" (the earlier segment).
        """
        stmt = (
            select(self.model_class)
            .where(
                ScheduleAssignment.week_id == week_id,
                ScheduleAssignment.position_id == position_id,
                ScheduleAssignment.day_index == day_index,
            )
            .order_by(ScheduleAssignment.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_segment(
        self,
        assignment_id: uuid.UUID,
        segment_start: str | None,
        segment_end: str | None,
    ) -> ScheduleAssignment | None:
        """Update an assignment's time segment; return the row with the guard
        eager-loaded, or None if it does not exist."""
        assignment = await self.session.get(ScheduleAssignment, assignment_id)
        if assignment is None:
            return None
        assignment.segment_start = segment_start
        assignment.segment_end = segment_end
        await self.session.flush()
        return await self.get_with_user(assignment_id)

    async def get_in_cell(
        self,
        week_id: uuid.UUID,
        position_id: uuid.UUID,
        day_index: int,
        user_id: uuid.UUID,
    ) -> ScheduleAssignment | None:
        """Return the assignment of a specific guard in a cell, or None."""
        stmt = select(self.model_class).where(
            ScheduleAssignment.week_id == week_id,
            ScheduleAssignment.position_id == position_id,
            ScheduleAssignment.day_index == day_index,
            ScheduleAssignment.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
