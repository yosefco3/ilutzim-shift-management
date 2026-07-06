"""
AttendanceShiftRepository — data access for paired actual shifts.

The table is derived: the pairing engine deletes a window and rebuilds it, so
this repository exposes window-scoped delete/list plus the stale-open sweep.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import delete as sa_delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.attendance.constants import ShiftPairStatus
from app.attendance.models.attendance_shift import AttendanceShift
from app.repositories.base_repository import BaseRepository


class AttendanceShiftRepository(BaseRepository[AttendanceShift]):
    """Data-access operations for AttendanceShift."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AttendanceShift)

    async def delete_window(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> None:
        """Drop all derived rows for a user in [date_from, date_to] (rebuild)."""
        await self.session.execute(
            sa_delete(AttendanceShift).where(
                AttendanceShift.user_id == user_id,
                AttendanceShift.work_date >= date_from,
                AttendanceShift.work_date <= date_to,
            )
        )

    async def list_for_user(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[AttendanceShift]:
        """A user's shifts in [date_from, date_to], chronological."""
        stmt = (
            select(AttendanceShift)
            .where(
                AttendanceShift.user_id == user_id,
                AttendanceShift.work_date >= date_from,
                AttendanceShift.work_date <= date_to,
            )
            .order_by(AttendanceShift.check_in_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user_with_events(
        self, user_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[AttendanceShift]:
        """Like ``list_for_user`` but with in/out events eager-loaded
        (sources, locations and radius flags for the comparison layer)."""
        stmt = (
            select(AttendanceShift)
            .where(
                AttendanceShift.user_id == user_id,
                AttendanceShift.work_date >= date_from,
                AttendanceShift.work_date <= date_to,
            )
            .options(
                selectinload(AttendanceShift.in_event),
                selectinload(AttendanceShift.out_event),
            )
            .order_by(AttendanceShift.check_in_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_date_with_events(self, work_date: date) -> list[AttendanceShift]:
        """All users' shifts for one work_date, events eager-loaded (day view)."""
        stmt = (
            select(AttendanceShift)
            .where(AttendanceShift.work_date == work_date)
            .options(
                selectinload(AttendanceShift.in_event),
                selectinload(AttendanceShift.out_event),
            )
            .order_by(AttendanceShift.check_in_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_open_for_user(self, user_id: uuid.UUID) -> AttendanceShift | None:
        """The user's most recent OPEN shift, if any.

        OPEN is inherently recent (the sweep flips anything past the 16h
        ceiling), so no date window is needed. Drives the smart direction
        confirmation in the bot.
        """
        stmt = (
            select(AttendanceShift)
            .where(
                AttendanceShift.user_id == user_id,
                AttendanceShift.status == ShiftPairStatus.OPEN,
            )
            .order_by(AttendanceShift.check_in_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def close_stale_open(self, cutoff: datetime, now: datetime) -> int:
        """OPEN shifts whose check-in predates ``cutoff`` → MISSING_OUT.

        Safety net for shifts outside the daily recompute window (e.g. the
        server slept for days). Returns the number of rows flipped.
        """
        result = await self.session.execute(
            update(AttendanceShift)
            .where(
                AttendanceShift.status == ShiftPairStatus.OPEN,
                AttendanceShift.check_in_at < cutoff,
            )
            .values(status=ShiftPairStatus.MISSING_OUT, recomputed_at=now)
        )
        return result.rowcount or 0
