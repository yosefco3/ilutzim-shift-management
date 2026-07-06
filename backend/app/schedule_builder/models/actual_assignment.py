"""
ActualAssignment model — one guard placed on an actual-board cell.

Mirror of :class:`ScheduleAssignment` re-pointed at the actual layer: the cell
is an :class:`ActualPosition` × day, and the row carries the same optional time
segment (``segment_start``/``segment_end``; null = the position's whole window
that day; ``end <= start`` wraps past midnight).

``actual_schedule_id`` is denormalised alongside ``actual_position_id`` so a
whole week loads in one indexed query.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.schedule_builder.models.actual_position import ActualPosition
    from app.schedule_builder.models.actual_schedule import ActualSchedule


class ActualAssignment(BaseModel):
    """One guard on an actual position×day (optionally a time segment)."""

    # Owning actual schedule (denormalised for one-query week loads).
    # CASCADE: deleting the copy drops its assignments.
    actual_schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actual_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The actual position (board row) being filled. CASCADE: removing a
    # position mid-week drops its assignments — that's the "drop a position"
    # story working as intended.
    actual_position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actual_positions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Day-of-week column: 0=ראשון … 6=שבת (matches day_schedules keys).
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # The assigned guard. CASCADE: deleting a guard drops their assignments.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional time segment 'HH:MM' (null = the position's whole window that
    # day). end <= start wraps past midnight.
    segment_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    segment_end: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # Relationships (read-only convenience).
    actual_schedule: Mapped["ActualSchedule"] = relationship()
    actual_position: Mapped["ActualPosition"] = relationship()
    user: Mapped["User"] = relationship()

    @property
    def position_id(self) -> uuid.UUID:
        """Alias so the shared WeekSchedule core (which keys assignments by
        ``position_id``) consumes planned and actual assignments identically."""
        return self.actual_position_id

    __table_args__ = (
        # A cell may hold several guards (tiling / events), but never the *same*
        # guard twice.
        UniqueConstraint(
            "actual_position_id", "day_index", "user_id",
            name="uq_actual_assignment_cell_user",
        ),
    )
