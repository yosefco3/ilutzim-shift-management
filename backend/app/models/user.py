"""
User model — security guards.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.weekly_submission import WeeklySubmission

# Postgres stores this as JSONB; SQLite (tests) falls back to generic JSON.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class User(BaseModel):
    """Security guard profile."""

    phone_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False,
    )
    telegram_id: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True,
    )
    first_name: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    # Guard attributes (e.g. ["AHMASH", "PATROL_VEHICLE"]) — a guard may hold
    # several at once. Stored as a JSON list of UserRole values.
    roles: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default="[]",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
    )
    # "מתגבר" — an ad-hoc external reinforcement guard, created from the actual
    # board for one specific week. NOT part of the organic team: excluded from
    # get_active_users (so the attendance comparison, payroll, broadcasts and
    # the planning read models never see them), hidden from the guards page,
    # never submits availability and never punches. Their assignments exist
    # only on the actual schedule (and its Excel).
    is_reinforcement: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    exemptions_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    min_total_shifts: Mapped[int] = mapped_column(
        Integer, default=0,
    )
    min_night_shifts: Mapped[int] = mapped_column(
        Integer, default=0,
    )
    min_evening_shifts: Mapped[int] = mapped_column(
        Integer, default=0,
    )

    # Optional preferred shift (ShiftType value: morning/afternoon/night).
    # Informational for now — input to the future auto-scheduler.
    preferred_shift: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Stage 3 (attendance): when the guard confirmed the one-time GPS-consent
    # message in the bot. NULL = not yet consented → the punch flow shows the
    # consent message before requesting a location. Read-only in the admin UI.
    gps_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Stage 3 (payroll / י.ל.מ report headers). national_id is PREPARED ONLY
    # (decision 4/7): the column exists, no UI exposes it yet — the report
    # prints it when present, blank otherwise.
    payroll_employee_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payroll_ylm_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    weekly_submissions: Mapped[list["WeeklySubmission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_users_phone_number", "phone_number"),
        Index("ix_users_telegram_id", "telegram_id"),
    )