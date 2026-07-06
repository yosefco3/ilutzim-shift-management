"""
AttendanceAdjustment model — the admin's audit trail (stage 3 / 02).

Every manual correction is a row here: what was done (action), to whom, on
which day, the before/after values and a free-text reason. The raw punch log
is never mutated — a "void" or "edit" is expressed as an adjustment row whose
``target_event_id`` marks the punch as superseded; the derived shifts are then
recomputed from the *effective* (non-superseded) events. Single-admin model:
no approval chain — this trail IS the approval.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.attendance.constants import AdjustmentAction
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User

# Postgres stores this as JSONB; SQLite (tests) falls back to generic JSON.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class AttendanceAdjustment(BaseModel):
    """One admin correction, with its full context."""

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    work_date: Mapped[date] = mapped_column(Date, nullable=False)

    action: Mapped[AdjustmentAction] = mapped_column(
        Enum(AdjustmentAction, name="adjustment_action"),
        nullable=False,
    )

    # The punch this adjustment supersedes (EDIT_TIME / VOID_PUNCH) or created
    # (ADD_PUNCH). NULL for MARK_ABSENCE.
    target_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attendance_events.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Human-readable snapshots for the tooltip/history view.
    before: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    reason: Mapped[str] = mapped_column(String(500), nullable=False)

    user: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_attendance_adjustments_user_date", "user_id", "work_date"),
        Index("ix_attendance_adjustments_target", "target_event_id"),
    )
