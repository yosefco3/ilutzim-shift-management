"""
Procedure model — a security procedure (סד"פ).

Created by an admin from pasted text or an uploaded docx. Lives as a DRAFT
while questions are generated/edited, then PUBLISHED (broadcast + quiz live)
and eventually ARCHIVED. The body is plain Text so it can be long.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.procedures.constants import ProcedureStatus

if TYPE_CHECKING:
    from app.procedures.models.quiz_question import QuizQuestion


class Procedure(BaseModel):
    """One security procedure + its AI-generated quiz bank."""

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Sanitized HTML snapshot of the uploaded docx (mammoth → nh3), rendered by
    # the guard WebApp reading page. NULL for plain-text-pasted procedures and
    # for procedures created before this feature — the page then falls back to
    # ``body_text``. It is a frozen snapshot: the admin plain-text editor edits
    # only ``body_text``, so ``body_html`` stays in sync only with the uploaded
    # docx (a re-upload replaces both).
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Original filename when the body was extracted from an uploaded docx
    # (None when the admin pasted the text directly).
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ProcedureStatus] = mapped_column(
        Enum(ProcedureStatus, name="procedure_status"),
        nullable=False,
        default=ProcedureStatus.DRAFT,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Exactly one procedure may be the current/default (הנוהל הנוכחי): the bot
    # list surfaces it first with a ⭐ and the reminder job targets only it.
    # Enforced by the partial unique index below. 'false' (PG literal), not
    # '1'/'0' — PG rejects an integer default on a boolean column.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.display_order",
    )

    __table_args__ = (
        # Partial unique index: at most one default procedure. Emitted for both
        # dialects so it holds in SQLite tests and PostgreSQL prod (same pattern
        # as uq_quiz_attempt_one_in_progress).
        Index(
            "uq_procedure_single_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default"),
        ),
    )
