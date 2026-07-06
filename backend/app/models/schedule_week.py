"""
ScheduleWeek model — represents a weekly scheduling period.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import WeekStatus
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.weekly_submission import WeeklySubmission


class ScheduleWeek(BaseModel):
    """Weekly schedule period."""

    # Two structural guards for the week lifecycle (also created by the
    # d3f7a1b9c2e4 migration for prod, and by create_all for the test DB):
    #  - uq_schedule_weeks_date_range: no two weeks share a (start_date, end_date)
    #    — blocks the concurrent auto_rotate_weeks duplicate-week race (B-4).
    #  - uq_one_open_week: a partial unique index enforcing at most one OPEN week
    #    (single-open invariant, B-1). The status enum is stored by member NAME, so
    #    the predicate is uppercase 'OPEN' on both Postgres and SQLite.
    __table_args__ = (
        UniqueConstraint("start_date", "end_date", name="uq_schedule_weeks_date_range"),
        Index(
            "uq_one_open_week",
            "status",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
            sqlite_where=text("status = 'OPEN'"),
        ),
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[WeekStatus] = mapped_column(
        Enum(WeekStatus, name="week_status"),
        nullable=False,
        default=WeekStatus.OPEN,
    )
    # Set the first time the week enters OPEN. NULL = never opened, which is how
    # the auto-open cron distinguishes a fresh week from one whose submission
    # window already ran (now CLOSED again) — so it is never auto-reopened.
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stamped each time the admin presses "publish" (broadcasts personal
    # schedules). NULL = never published. Publish keeps the week CLOSED — it
    # never locks — so this timestamp is the ONLY signal that a week's schedule
    # was already broadcast; the admin UI uses it for "publish" vs "re-publish".
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    weekly_submissions: Mapped[list["WeeklySubmission"]] = relationship(
        back_populates="week", cascade="all, delete-orphan",
        passive_deletes=True,
    )