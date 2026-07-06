"""
AttendanceEventRepository — data access for the raw punch log.

Append-only by design: exposes ``add`` and read queries. The inherited
``update``/``delete`` of ``BaseRepository`` are deliberately overridden to
raise — nothing in the application may mutate the raw log.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.attendance.constants import PunchDirection
from app.attendance.models.attendance_event import AttendanceEvent
from app.repositories.base_repository import BaseRepository


class AttendanceEventRepository(BaseRepository[AttendanceEvent]):
    """Data-access operations for AttendanceEvent (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AttendanceEvent)

    async def add(self, **kwargs) -> AttendanceEvent:
        """Append a new punch event (alias of create, the only write path)."""
        return await self.create(**kwargs)

    async def list_for_user(
        self, user_id: uuid.UUID, from_dt: datetime, to_dt: datetime
    ) -> list[AttendanceEvent]:
        """All events for a user in [from_dt, to_dt), oldest first."""
        stmt = (
            select(AttendanceEvent)
            .where(
                AttendanceEvent.user_id == user_id,
                AttendanceEvent.punched_at >= from_dt,
                AttendanceEvent.punched_at < to_dt,
            )
            .order_by(AttendanceEvent.punched_at.asc(), AttendanceEvent.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def exists_similar(
        self,
        user_id: uuid.UUID,
        direction: PunchDirection,
        punched_at: datetime,
        window_minutes: int,
    ) -> AttendanceEvent | None:
        """Return a same-direction event within ±window of punched_at, if any.

        Used for double-tap dedup: the caller shows "already recorded at HH:MM"
        instead of appending a duplicate.
        """
        lo = punched_at - timedelta(minutes=window_minutes)
        hi = punched_at + timedelta(minutes=window_minutes)
        stmt = (
            select(AttendanceEvent)
            .where(
                AttendanceEvent.user_id == user_id,
                AttendanceEvent.direction == direction,
                AttendanceEvent.punched_at >= lo,
                AttendanceEvent.punched_at <= hi,
            )
            .order_by(AttendanceEvent.punched_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_effective_for_user(
        self, user_id: uuid.UUID, from_dt: datetime, to_dt: datetime
    ) -> list[AttendanceEvent]:
        """Like ``list_for_user`` but WITHOUT superseded punches.

        A punch is superseded when an adjustment (VOID_PUNCH or EDIT_TIME)
        targets it. This is the feed for the pairing engine and the anomaly
        layer — the raw list stays available for audit views.
        """
        from app.attendance.constants import AdjustmentAction
        from app.attendance.models.attendance_adjustment import AttendanceAdjustment

        superseded = (
            select(AttendanceAdjustment.target_event_id)
            .where(
                AttendanceAdjustment.target_event_id.isnot(None),
                AttendanceAdjustment.action.in_(
                    [AdjustmentAction.VOID_PUNCH, AdjustmentAction.EDIT_TIME]
                ),
            )
            .scalar_subquery()
        )
        stmt = (
            select(AttendanceEvent)
            .where(
                AttendanceEvent.user_id == user_id,
                AttendanceEvent.punched_at >= from_dt,
                AttendanceEvent.punched_at < to_dt,
                AttendanceEvent.id.not_in(superseded),
            )
            .order_by(AttendanceEvent.punched_at.asc(), AttendanceEvent.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def event_dates_for_user(self, user_id: uuid.UUID, date_from, date_to) -> list:
        """Distinct calendar days on which the user has any punch (period feed
        must include punch-only days — e.g. an orphan OUT with no shift)."""
        from datetime import datetime as dt, time as time_type, timedelta

        lo = dt.combine(date_from, time_type.min)
        hi = dt.combine(date_to, time_type.min) + timedelta(days=1)
        stmt = (
            select(AttendanceEvent.punched_at)
            .where(
                AttendanceEvent.user_id == user_id,
                AttendanceEvent.punched_at >= lo,
                AttendanceEvent.punched_at < hi,
            )
        )
        result = await self.session.execute(stmt)
        return sorted({row.date() for row in result.scalars().all()})

    async def count_since(self, from_dt: datetime) -> int:
        """Number of events punched at/after ``from_dt`` (status widget)."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(AttendanceEvent.id)).where(
                AttendanceEvent.punched_at >= from_dt
            )
        )
        return int(result.scalar() or 0)

    async def last_event_at(self) -> datetime | None:
        """Timestamp of the most recent punch (status widget)."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.max(AttendanceEvent.punched_at))
        )
        return result.scalar()

    async def distinct_user_ids(
        self, from_dt: datetime, to_dt: datetime
    ) -> list[uuid.UUID]:
        """User ids with at least one event in [from_dt, to_dt) — sweep input."""
        stmt = (
            select(AttendanceEvent.user_id)
            .where(
                AttendanceEvent.punched_at >= from_dt,
                AttendanceEvent.punched_at < to_dt,
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── The raw log is immutable ─────────────────────────────────────────────
    async def update(self, id: uuid.UUID, **kwargs) -> AttendanceEvent:
        raise RuntimeError("attendance_events is append-only — updates are forbidden")

    async def delete(self, id: uuid.UUID) -> bool:
        raise RuntimeError("attendance_events is append-only — deletes are forbidden")
