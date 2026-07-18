"""
ProcedureReadReceipt model — records that a guard first opened a procedure's
WebApp reading page.

A unique ``(procedure_id, user_id)`` pair so the first-open timestamp is recorded
once: re-opens (double-open, refresh, revisit) never duplicate the row and never
overwrite the original timestamp. Mirrors ``ProcedureReminderSent``'s shape. The
FK to ``procedures`` cascades on hard-delete (the same erasure philosophy as the
existing history cascade); the FK to ``users`` cascades on guard deletion.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ProcedureReadReceipt(BaseModel):
    """The first time a guard opened a procedure's WebApp reading page."""

    __tablename__ = "procedure_read_receipts"

    procedure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    first_read_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "procedure_id", "user_id", name="uq_procedure_read_once"
        ),
    )
