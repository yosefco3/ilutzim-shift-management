"""
SavedSchedule model — part B (schedule builder).

A **saved schedule** (סידור שמור) is a *frozen, self-contained snapshot* of a
week's built schedule (the board + its assignments), captured on demand when the
admin presses "שמור סידור". It exists so the finished schedule can be downloaded
from the Weeks page long after it was built — and, crucially, **survives deletion
of the activation profile it was built from**.

Why this model has no profile/position FK
-----------------------------------------
The live schedule is a set of ``schedule_assignments`` rows that FK-reference
``positions`` (``ondelete='CASCADE'``), which FK-reference the profile
(``ondelete='CASCADE'``). So deleting a profile cascades away positions →
assignments and the live schedule is gone. To make the saved schedule immune to
that, this table deliberately keeps **no link to profile or position** — the
position names, guard names, days, windows and time segments are all copied
*inline* into ``snapshot``. The only FK is ``week_id`` (``ondelete='CASCADE'``):
the snapshot is removed only if the *week itself* is deleted.

One snapshot per week: ``week_id`` is UNIQUE — re-saving overwrites (see
``SavedScheduleRepository.upsert``). ``updated_at`` (from ``BaseModel``) is the
"last saved" time.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.schedule_week import ScheduleWeek

# Postgres stores this as JSONB; SQLite (tests) falls back to generic JSON.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class SavedSchedule(BaseModel):
    """A frozen, self-contained snapshot of a week's built schedule."""

    # The week this snapshot belongs to — the ONLY foreign key. CASCADE: the
    # snapshot dies only if the week itself is deleted. UNIQUE: one snapshot per
    # week (re-saving upserts).
    week_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_weeks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Name of the profile the snapshot was built from, copied inline for display.
    # NOT a link — the profile may later be deleted; this string still stands.
    profile_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The full self-contained render payload (positions × days with inline
    # position names, guard names, windows and time segments). Shape is built by
    # SavedScheduleService.save and consumed by ExcelExportService.render_saved_schedule.
    snapshot: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}",
    )

    # Read-only convenience relationship (no back_populates — keeps part A clean).
    week: Mapped["ScheduleWeek"] = relationship()
