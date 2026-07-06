"""
ActualPosition model — a position row owned by one week's actual schedule.

A field-for-field mirror of :class:`Position` minus ``profile_id``: the actual
schedule owns a **private copy** of its positions ("a profile that starts with
all the data"), so mid-week edits — changed hours, a dropped day, a whole ad-hoc
position for an unplanned event — never touch the shared profile or other weeks.

``source_position_id`` is a *soft* pointer back to the planned position it was
copied from (no FK — the profile position may be edited or deleted later without
affecting this copy). ``None`` marks an ad-hoc position added mid-week.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.schedule_builder.models.actual_schedule import ActualSchedule

# Postgres stores these as JSONB; SQLite (tests) falls back to generic JSON.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class ActualPosition(BaseModel):
    """One row of the actual (execution) board."""

    # Owning actual schedule. CASCADE: deleting the copy drops its positions.
    actual_schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actual_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Display name (e.g. "ארנונה", "קומה 6", "אבטחת אירוע במתנ\"ס").
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Per-day hours + active days in one map: day index ("0".."6") -> {start,end}.
    # Presence of a key = active that day; missing = inactive.
    day_schedules: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}",
    )

    # Required attribute keys — copied for display parity with the planned board.
    # The actual board enforces nothing (free editing), so this is informational.
    required_attributes: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default="[]",
    )

    # Display order within the actual board.
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    # Event / non-splitting position — same semantics as Position.is_event.
    is_event: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )

    # Event positions only: fixed participant count (None = unlimited). Same
    # semantics as Position.event_required_count.
    event_required_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
    )

    # Soft pointer to the planned Position this row was copied from. No FK on
    # purpose — the source may change or vanish without touching the copy.
    # None = ad-hoc position added mid-week.
    source_position_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, default=None,
    )

    actual_schedule: Mapped["ActualSchedule"] = relationship(
        back_populates="positions"
    )
