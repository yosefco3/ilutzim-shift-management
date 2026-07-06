"""
WeekProfileAssignment model — part B (schedule builder).

Binds one ``ScheduleWeek`` (part A) to one ``ActivationProfile`` (part B): a week
is built from exactly one profile. The "שגרה" template is shared across many
weeks; a special week (e.g. a mid-week holiday) gets its own duplicated profile.

This link lives in **part B** (not as a column on ``ScheduleWeek``) to preserve
the one-way dependency rule: part B may reference part A, never the reverse. The
FK to ``schedule_weeks`` is therefore the allowed B → A direction.

A week with no row here falls back to the default profile (``is_default``). The
``week_id`` is **unique** — at most one explicit assignment per week. Deleting
either side cascades the assignment away (the week then reverts to the default).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.schedule_week import ScheduleWeek
    from app.schedule_builder.models.activation_profile import ActivationProfile


class WeekProfileAssignment(BaseModel):
    """One week ↔ one activation profile."""

    # The bound week (part A). Unique: at most one assignment per week.
    week_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_weeks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # The profile this week is built from. Deleting the profile drops the
    # assignment, and the week falls back to the default profile.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activation_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    profile: Mapped["ActivationProfile"] = relationship()
    week: Mapped["ScheduleWeek"] = relationship()
