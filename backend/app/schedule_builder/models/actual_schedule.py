"""
ActualSchedule model — the "סידור בפועל" layer (actual-schedule feature, step 01).

The planning board freezes the moment a week starts (the Sunday rollover). But
reality keeps moving: a guard cancels day-of, an unplanned event needs an extra
position, a position is dropped. The **actual schedule** is a private, editable
copy of the planned schedule, seeded 1:1 at rollover (or lazily for weeks that
predate the feature), and it is what the attendance comparison — and everything
downstream of it (payroll norm, admin alerts, payroll reports) — reads from.

One row per week (``week_id`` UNIQUE). The copy owns its positions outright
(:class:`ActualPosition`) rather than pointing at the shared profile positions,
so mid-week edits never leak into other weeks or the profile. Editing has **no
time gate**: ended weeks stay editable for retroactive payroll fixes.

The planning layer (profiles/positions/schedule_assignments/saved_schedules) is
never touched by this module.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.schedule_week import ScheduleWeek
    from app.schedule_builder.models.actual_position import ActualPosition


class ActualSchedule(BaseModel):
    """The editable execution copy of one week's schedule (one per week)."""

    # The week this copy belongs to. UNIQUE — a week has at most one actual
    # schedule. CASCADE: deleting the week (retention purge) drops the copy.
    week_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_weeks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # When the copy was seeded from the planned schedule.
    seeded_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # How the copy came to exist — "rollover" (the week-start hook) or "lazy"
    # (first access to a week that predates the feature / missed rollover).
    # Diagnostic only; never drives behaviour.
    seed_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="lazy", server_default="lazy",
    )

    week: Mapped["ScheduleWeek"] = relationship()
    positions: Mapped[list["ActualPosition"]] = relationship(
        back_populates="actual_schedule",
        cascade="all, delete-orphan",
        order_by="ActualPosition.display_order",
    )
