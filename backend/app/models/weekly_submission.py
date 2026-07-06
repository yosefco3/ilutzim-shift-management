"""
WeeklySubmission model — guard's weekly availability submission.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.daily_status import DailyStatus
    from app.models.schedule_week import ScheduleWeek
    from app.models.user import User


class WeeklySubmission(BaseModel):
    """Guard's availability submission for a specific week."""

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False,
    )
    week_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_weeks.id", ondelete="CASCADE"), nullable=False,
    )
    general_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_deviation: Mapped[bool] = mapped_column(Boolean, default=False)
    # Admin acknowledged the guard's rule violations for this submission, so the
    # UI hides the violation marker. Computed warnings still exist; this just
    # records that an admin reviewed and accepted them.
    violation_acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="weekly_submissions")
    week: Mapped["ScheduleWeek"] = relationship(back_populates="weekly_submissions")
    daily_statuses: Mapped[list["DailyStatus"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "week_id", name="uq_user_week_submission"),
    )