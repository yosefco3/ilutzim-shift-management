"""
Procedure model — a security procedure (סד"פ).

Created by an admin from pasted text or an uploaded docx. Lives as a DRAFT
while questions are generated/edited, then PUBLISHED (broadcast + quiz live)
and eventually ARCHIVED. The body is plain Text so it can be long.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.procedures.constants import ProcedureStatus

if TYPE_CHECKING:
    from app.procedures.models.quiz_question import QuizQuestion


class Procedure(BaseModel):
    """One security procedure + its AI-generated quiz bank."""

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Original filename when the body was extracted from an uploaded docx
    # (None when the admin pasted the text directly).
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ProcedureStatus] = mapped_column(
        Enum(ProcedureStatus, name="procedure_status"),
        nullable=False,
        default=ProcedureStatus.DRAFT,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.display_order",
    )
