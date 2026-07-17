"""
QuizAttempt model — one guard's run through a procedure's quiz.

Stores the sampled question subset (``question_ids``) and the per-question
answer record (``answers``: ``{question_id: {selected, correct}}``), so the
attempt is a frozen snapshot: later edits/disables of the bank can't corrupt a
finished attempt's history.

A **partial unique index** on ``(user_id, procedure_id) WHERE status =
'in_progress'`` guarantees at most one in-flight attempt per guard+procedure.
This is the backstop for the double-"start quiz" race (two concurrent callback
taps): the second tap's INSERT hits ``IntegrityError`` and the handler recovers
the surviving attempt instead of sending question 1 twice.
"""

from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.procedures.constants import AttemptStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.procedures.models.procedure import Procedure

JSONType = JSON().with_variant(JSONB(), "postgresql")


class QuizAttempt(BaseModel):
    """One guard's attempt at a procedure's quiz (sampled subset, scored)."""

    procedure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Ordered list of sampled question ids (the snapshot taken at start time).
    question_ids: Mapped[list] = mapped_column(JSONType, nullable=False)
    # {question_id (str): {"selected": int, "correct": bool}} — selected is the
    # ORIGINAL option index; correct was computed at answer time.
    answers: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="quiz_attempt_status"),
        nullable=False,
        default=AttemptStatus.IN_PROGRESS,
    )

    procedure: Mapped["Procedure"] = relationship()
    user: Mapped["User"] = relationship()

    __table_args__ = (
        # Partial unique index: at most one IN_PROGRESS attempt per
        # (user, procedure). SQLAlchemy stores the enum NAME, so the WHERE
        # clause matches the stored literal. Emitted for both dialects so it
        # holds in SQLite tests and PostgreSQL prod.
        Index(
            "uq_quiz_attempt_one_in_progress",
            "user_id",
            "procedure_id",
            unique=True,
            postgresql_where=text("status = 'IN_PROGRESS'"),
            sqlite_where=text("status = 'IN_PROGRESS'"),
        ),
        Index("ix_quiz_attempt_user_procedure", "user_id", "procedure_id"),
    )
