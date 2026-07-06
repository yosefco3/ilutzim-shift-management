"""
ScheduleAssignment model — part B (schedule builder, task 05).

One **assignment** fills a board cell: a guard placed on a position×day for a
specific week. This is the layer that turns the read-only board skeleton (04)
into an actual schedule.

A cell (week×position×day) may hold **several** assignments — a coverage window
can be *tiled* between guards, each with its own optional time segment
(``segment_start``/``segment_end``; null = the position's whole window that day).
The current UI assigns a single guard per cell for simplicity, but the model
supports tiling so a future drag/tiling UI needs no migration. Coverage (the
union of segments vs the position window) is computed in task 06.

Dependency direction: this part-B table FK-references ``schedule_weeks`` and
``users`` (part A) — the allowed B → A direction. The soft link to the position
(part B) is a hard FK with CASCADE.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.schedule_week import ScheduleWeek
    from app.models.user import User
    from app.schedule_builder.models.position import Position


class ScheduleAssignment(BaseModel):
    """One guard placed on a position×day for a week (optionally a time segment)."""

    # The week this assignment belongs to (part A). CASCADE: deleting the week
    # drops its assignments.
    week_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_weeks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The position (board row) being filled. CASCADE: deleting a position drops
    # its assignments.
    position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Day-of-week column: 0=ראשון … 6=שבת (matches Position.day_schedules keys).
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # The assigned guard (part A). CASCADE: deleting a guard drops their
    # assignments.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional time segment 'HH:MM' (null = the position's whole window that day).
    # Lets one cell be tiled between guards (e.g. night 19:00–07:00 split into
    # 19:00–01:00 + 01:00–07:00). end <= start wraps past midnight.
    segment_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    segment_end: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # Relationships (read-only convenience; no back_populates to keep part A clean).
    week: Mapped["ScheduleWeek"] = relationship()
    position: Mapped["Position"] = relationship()
    user: Mapped["User"] = relationship()

    __table_args__ = (
        # A cell may hold several guards (tiling), but never the *same* guard
        # twice. Tiling between distinct guards stays allowed.
        UniqueConstraint(
            "week_id", "position_id", "day_index", "user_id",
            name="uq_assignment_cell_user",
        ),
    )
