"""
AttendanceEvent model — the raw punch log (stage 3, attendance).

**Append-only.** A row here is exactly what happened at the clock face: who,
which direction, when, from which source, and (for Telegram punches) where.
Rows are never updated or deleted by application code — corrections are made
as *new* ``manual`` events plus an ``attendance_adjustments`` audit record
(stage 3 / 02), and derived tables (``attendance_shifts``) are recomputed from
this log. That makes every payroll number reproducible from raw evidence.

``punched_at`` is naive local Israel time, like every other datetime in the
project (see ``app.utils.date_utils.now_il``).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.attendance.constants import PunchDirection, PunchSource
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class AttendanceEvent(BaseModel):
    """One raw IN/OUT punch."""

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    direction: Mapped[PunchDirection] = mapped_column(
        Enum(PunchDirection, name="punch_direction"),
        nullable=False,
    )

    punched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    source: Mapped[PunchSource] = mapped_column(
        Enum(PunchSource, name="punch_source"),
        nullable=False,
    )

    # Location of the punch moment only (Telegram punches). No continuous
    # tracking exists anywhere in the system.
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Distance from the configured site at punch time; NULL when the site
    # coordinates are not configured (or the punch carries no location).
    # out_of_radius marks-but-never-blocks (decision 2026-07-04).
    distance_from_site_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    out_of_radius: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Free-text note — used by MANUAL events (e.g. the admin's entry reason).
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # True only for MANUAL events created by the admin.
    created_by_admin: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    user: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_attendance_events_user_punched", "user_id", "punched_at"),
    )
