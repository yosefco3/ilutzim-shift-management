"""
AttendanceShift model — a paired actual shift (stage 3, attendance).

**Derived, always recomputable.** Rows here are built by the pairing engine
from the append-only ``attendance_events`` log: an IN punch opens a shift, the
matching OUT closes it. Recomputing a window deletes and rebuilds its rows —
nothing in this table is hand-edited, so it can never disagree with the raw
log. ``work_date`` is the attribution day: the day the shift STARTED (a night
shift crossing midnight belongs to the day of its check-in — decision 4/7).
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.attendance.constants import ShiftPairStatus
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.attendance.models.attendance_event import AttendanceEvent
    from app.models.user import User


class AttendanceShift(BaseModel):
    """One actual shift: a check-in, optionally closed by a check-out."""

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The day the shift is attributed to (= the check-in's calendar day).
    work_date: Mapped[date] = mapped_column(Date, nullable=False)

    check_in_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    in_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attendance_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    out_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attendance_events.id", ondelete="CASCADE"),
        nullable=True,
    )

    status: Mapped[ShiftPairStatus] = mapped_column(
        Enum(ShiftPairStatus, name="shift_pair_status"),
        nullable=False,
    )

    # When the pairing engine last (re)built this row.
    recomputed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship()
    in_event: Mapped["AttendanceEvent"] = relationship(foreign_keys=[in_event_id])
    # Nullable in practice (out_event_id may be NULL); annotated non-optional
    # because SQLAlchemy's de-stringify can't eval a PEP-604 union reliably.
    out_event: Mapped["AttendanceEvent"] = relationship(foreign_keys=[out_event_id])

    __table_args__ = (
        Index("ix_attendance_shifts_user_work_date", "user_id", "work_date"),
    )
