"""
DailyStatus model — guard's availability for a specific day.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.shift_window import ShiftWindow
    from app.models.weekly_submission import WeeklySubmission


class DailyStatus(BaseModel):
    """Guard's daily availability within a weekly submission."""

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("weekly_submissions.id", ondelete="CASCADE"), nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Relationships
    submission: Mapped["WeeklySubmission"] = relationship(back_populates="daily_statuses")
    shift_windows: Mapped[list["ShiftWindow"]] = relationship(
        back_populates="daily_status", cascade="all, delete-orphan",
    )
