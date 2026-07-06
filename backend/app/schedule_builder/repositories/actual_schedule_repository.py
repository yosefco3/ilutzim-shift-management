"""
ActualScheduleRepository — data access for the actual-schedule layer (step 02).

One repository for all the ``actual_*`` tables: they form a single aggregate
that is created, loaded and deleted together.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.schedule_builder.models.actual_assignment import ActualAssignment
from app.schedule_builder.models.actual_position import ActualPosition
from app.schedule_builder.models.actual_reinforcement import ActualReinforcement
from app.schedule_builder.models.actual_schedule import ActualSchedule


class ActualScheduleRepository(BaseRepository[ActualSchedule]):
    """Data-access operations for the actual-schedule aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ActualSchedule)

    async def get_by_week(self, week_id: uuid.UUID) -> ActualSchedule | None:
        """Return the week's actual schedule with its positions, or None."""
        stmt = (
            select(ActualSchedule)
            .where(ActualSchedule.week_id == week_id)
            .options(selectinload(ActualSchedule.positions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_positions(
        self, actual_schedule_id: uuid.UUID
    ) -> list[ActualPosition]:
        """All positions of one actual schedule, in display order."""
        stmt = (
            select(ActualPosition)
            .where(ActualPosition.actual_schedule_id == actual_schedule_id)
            .order_by(ActualPosition.display_order, ActualPosition.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_assignments(
        self, actual_schedule_id: uuid.UUID
    ) -> list[ActualAssignment]:
        """All assignments of one actual schedule (one indexed query)."""
        stmt = (
            select(ActualAssignment)
            .where(ActualAssignment.actual_schedule_id == actual_schedule_id)
            .options(selectinload(ActualAssignment.user))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_position(
        self, actual_position_id: uuid.UUID
    ) -> ActualPosition | None:
        return await self.session.get(ActualPosition, actual_position_id)

    async def list_reinforcements(
        self, actual_schedule_id: uuid.UUID
    ) -> list[ActualReinforcement]:
        """This week's reinforcement cards, with their users, by creation."""
        stmt = (
            select(ActualReinforcement)
            .where(ActualReinforcement.actual_schedule_id == actual_schedule_id)
            .options(selectinload(ActualReinforcement.user))
            .order_by(ActualReinforcement.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_reinforcement(
        self, card_id: uuid.UUID
    ) -> ActualReinforcement | None:
        stmt = (
            select(ActualReinforcement)
            .where(ActualReinforcement.id == card_id)
            .options(selectinload(ActualReinforcement.user))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reinforcement_assignments_between(
        self, start: date, end: date
    ) -> list[ActualAssignment]:
        """Reinforcement-guard assignments in weeks overlapping [start, end].

        Powers the reinforcements report. Weeks *overlapping* the range are a
        superset — an assignment's concrete date is ``week.start_date +
        day_index``, so the exact per-day filter happens in the caller.
        Everything the report needs rides along eager-loaded.
        """
        stmt = (
            select(ActualAssignment)
            .join(User, ActualAssignment.user_id == User.id)
            .join(
                ActualSchedule,
                ActualAssignment.actual_schedule_id == ActualSchedule.id,
            )
            .join(ScheduleWeek, ActualSchedule.week_id == ScheduleWeek.id)
            .where(User.is_reinforcement.is_(True))
            .where(ScheduleWeek.start_date <= end)
            .where(ScheduleWeek.end_date >= start)
            .options(
                selectinload(ActualAssignment.user),
                selectinload(ActualAssignment.actual_position),
                selectinload(ActualAssignment.actual_schedule)
                .selectinload(ActualSchedule.week),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_cards_for_schedules(
        self, schedule_ids: list[uuid.UUID]
    ) -> list[ActualReinforcement]:
        """All reinforcement cards of the given actual schedules (one query)."""
        if not schedule_ids:
            return []
        stmt = select(ActualReinforcement).where(
            ActualReinforcement.actual_schedule_id.in_(schedule_ids)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_assignment(
        self, actual_assignment_id: uuid.UUID
    ) -> ActualAssignment | None:
        return await self.session.get(ActualAssignment, actual_assignment_id)
