"""
ScheduleWeek repository — data access for weekly schedule periods.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.repositories.base_repository import BaseRepository


class ScheduleWeekRepository(BaseRepository[ScheduleWeek]):
    """Data-access operations for ScheduleWeek entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ScheduleWeek)

    async def get_current_open_week(self) -> ScheduleWeek | None:
        """Return the single OPEN week (the most recent one if data is corrupt).

        The ``uq_one_open_week`` partial index guarantees at most one OPEN week, so
        this normally returns 0 or 1 row. But this is a hot path (POST /submissions,
        current-week), so it must never raise ``MultipleResultsFound`` if two OPEN
        rows somehow exist — it deterministically picks the most recent by
        ``start_date`` (``limit(1)`` + ``scalar_one_or_none``) rather than crashing
        the guard-facing endpoints."""
        stmt = (
            select(self.model_class)
            .where(ScheduleWeek.status == WeekStatus.OPEN)
            .order_by(ScheduleWeek.start_date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_weeks_to_finalize_on_or_before(
        self, today: date
    ) -> list[ScheduleWeek]:
        """Return weeks the Sunday rollover should finalize to LOCKED.

        Any week whose ``start_date`` has arrived (``start_date <= today``) is no
        longer a relevant submission target and is finalized to LOCKED,
        **regardless of its current state** — OPEN, a CLOSED week that already
        ran its window (``opened_at IS NOT NULL``), or a CLOSED week that was
        never opened at all. A never-opened CLOSED week that already started is a
        stale ghost (nobody will ever submit for a week in the past); leaving it
        CLOSED both let its editing UI stay live and let it shadow the real
        upcoming candidate in ``get_upcoming_closed_week``, so it is locked too.

        The genuinely upcoming week (``start_date > today``) is untouched, so
        this never locks a future submission target. Already-LOCKED weeks are
        excluded (nothing to finalize). Ordered by start_date so the rollover is
        deterministic.
        """
        stmt = (
            select(self.model_class)
            .where(
                ScheduleWeek.start_date <= today,
                ScheduleWeek.status != WeekStatus.LOCKED,
            )
            .order_by(ScheduleWeek.start_date.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_week_containing(self, day: date) -> ScheduleWeek | None:
        """The week whose [start_date, end_date] range contains ``day``."""
        stmt = select(self.model_class).where(
            ScheduleWeek.start_date <= day,
            ScheduleWeek.end_date >= day,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_date_range(self, start: date, end: date) -> ScheduleWeek | None:
        """Find a week that exactly matches the given date range."""
        stmt = select(self.model_class).where(
            ScheduleWeek.start_date == start,
            ScheduleWeek.end_date == end,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_current_or_upcoming_week(self, today: date) -> ScheduleWeek | None:
        """Return the nearest week that has not ended yet (``end_date >= today``).

        Ordered by start_date ascending, so the *current* cycle wins over a
        later already-created week. Used to show the guard the week they most
        recently acted on (e.g. a locked current week) rather than next week.
        """
        stmt = (
            select(self.model_class)
            .where(ScheduleWeek.end_date >= today)
            .order_by(ScheduleWeek.start_date.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_upcoming_unstarted_week(self, today: date) -> ScheduleWeek | None:
        """Return the nearest week that has NOT started yet (``start_date > today``).

        This is the week the admin publishes: the upcoming week guards submitted
        for, finalized *before* it goes live. Ordered by start_date ascending so
        the soonest upcoming week wins over a further-out one. Once a week starts
        it is no longer a publish target, so it is excluded here.
        """
        stmt = (
            select(self.model_class)
            .where(ScheduleWeek.start_date > today)
            .order_by(ScheduleWeek.start_date.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_upcoming_closed_week(self, today: date) -> ScheduleWeek | None:
        """Return the nearest never-opened CLOSED week that has not STARTED yet.

        This is the next week the auto-open cron would open for submissions.
        ``opened_at IS NULL`` excludes a week that already had its submission
        window and was returned to CLOSED — the cron must never auto-reopen it
        (an admin still can, manually). ``start_date > today`` matches the OPEN
        gate in ``change_week_status``: a week that already started can never be
        opened, so a stale never-opened week must not shadow the real upcoming
        candidate (it would make auto-open fail silently for the whole cycle).
        Ordered by start_date ascending so the soonest candidate wins.
        """
        stmt = (
            select(self.model_class)
            .where(
                ScheduleWeek.status == WeekStatus.CLOSED,
                ScheduleWeek.start_date > today,
                ScheduleWeek.opened_at.is_(None),
            )
            .order_by(ScheduleWeek.start_date.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_week(self) -> ScheduleWeek | None:
        """Return the most recent week (by start_date), regardless of status."""
        stmt = (
            select(self.model_class)
            .order_by(ScheduleWeek.start_date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count(self) -> int:
        """Return the total number of weeks."""
        result = await self.session.execute(select(func.count(ScheduleWeek.id)))
        return result.scalar()

    async def get_weeks_beyond_retention(self, keep: int) -> list[ScheduleWeek]:
        """Return weeks older than the ``keep`` most-recent ones (purge candidates).

        Weeks are ordered by ``start_date`` descending and the first ``keep`` are
        retained; everything past that offset is returned for deletion. A
        non-positive ``keep`` returns an empty list (safety — never purge all).
        """
        if keep <= 0:
            return []
        stmt = (
            select(self.model_class)
            .order_by(ScheduleWeek.start_date.desc())
            .offset(keep)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, week_id: uuid.UUID, new_status: WeekStatus
    ) -> ScheduleWeek:
        """Transition a week to a new status."""
        return await self.update(week_id, status=new_status)
