"""
ProcedureReminderSent model — one-reminder-per-guard ledger for procedures.

Mirrors ``AttendanceAlertSent``: a unique ``(procedure_id, user_id)`` pair so
the daily reminder job (which re-runs) sends each guard at most ONE reminder per
procedure, regardless of how many times the job fires.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ProcedureReminderSent(BaseModel):
    """Records that a guard has already been reminded about a procedure."""

    __tablename__ = "procedure_reminders_sent"

    procedure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "procedure_id", "user_id", name="uq_procedure_reminder_once"
        ),
    )
