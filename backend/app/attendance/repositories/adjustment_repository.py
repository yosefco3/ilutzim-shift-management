"""
AttendanceAdjustmentRepository — data access for the admin audit trail.
Append-only like the raw log (a correction is never edited — a new one is
appended on top).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.attendance.constants import AdjustmentAction
from app.attendance.models.attendance_adjustment import AttendanceAdjustment
from app.repositories.base_repository import BaseRepository


class AttendanceAdjustmentRepository(BaseRepository[AttendanceAdjustment]):
    """Data-access operations for AttendanceAdjustment (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AttendanceAdjustment)

    async def add(self, **kwargs) -> AttendanceAdjustment:
        return await self.create(**kwargs)

    async def list_for_user_day(
        self, user_id: uuid.UUID, work_date: date
    ) -> list[AttendanceAdjustment]:
        stmt = (
            select(AttendanceAdjustment)
            .where(
                AttendanceAdjustment.user_id == user_id,
                AttendanceAdjustment.work_date == work_date,
            )
            .order_by(AttendanceAdjustment.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def has_absence_approval(
        self, user_id: uuid.UUID, work_date: date
    ) -> bool:
        stmt = (
            select(AttendanceAdjustment.id)
            .where(
                AttendanceAdjustment.user_id == user_id,
                AttendanceAdjustment.work_date == work_date,
                AttendanceAdjustment.action == AdjustmentAction.MARK_ABSENCE,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    # ── append-only ──────────────────────────────────────────────────────────
    async def update(self, id: uuid.UUID, **kwargs) -> AttendanceAdjustment:
        raise RuntimeError("attendance_adjustments is append-only")

    async def delete(self, id: uuid.UUID) -> bool:
        raise RuntimeError("attendance_adjustments is append-only")
