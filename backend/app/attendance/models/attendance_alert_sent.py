"""
AttendanceAlertSent model — idempotency ledger for admin alerts (stage 3 / 02).

One row per (alert_type, user, ref_key) — the scheduler job runs every few
minutes, and this unique key guarantees each incident alerts the admin exactly
once, no matter how many times the check re-runs.
"""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AttendanceAlertSent(BaseModel):
    """A single dispatched admin alert."""

    __tablename__ = "attendance_alerts_sent"

    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)  # no_show | long_shift | short_rest
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ref_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Disambiguates within a day: planned-start for no_show, shift id otherwise.
    ref_key: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "alert_type", "user_id", "ref_key", name="uq_attendance_alert_once"
        ),
    )
