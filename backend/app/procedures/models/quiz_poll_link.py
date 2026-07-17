"""
QuizPollLink model — maps a Telegram quiz poll back to its attempt+question.

Telegram ``PollAnswer`` updates carry only ``poll_id`` + the chosen option ids,
never the question or which answer was correct. So each quiz poll we send gets
a row here recording: which attempt + question it belongs to, the shuffled
option order shown to the guard (``option_order``), and the correct option's
position *in that shuffled order* (``correct_option_id``). Persisted (not
in-memory) so a bot restart mid-quiz — a Railway redeploy — does not lose the
poll→question mapping; a delayed PollAnswer after restart still resolves.

``telegram_poll_id`` is the primary key (it is globally unique per Telegram
poll and is exactly the key the PollAnswer handler looks up by), so this model
deliberately does NOT use the UUID ``BaseModel`` PK.
"""

from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.procedures.models.quiz_attempt import QuizAttempt

JSONType = JSON().with_variant(JSONB(), "postgresql")


class QuizPollLink(Base):
    """One sent quiz poll ↔ its attempt/question + shuffled answer mapping."""

    __tablename__ = "quiz_poll_links"

    telegram_poll_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False
    )
    # Permutation: option_order[shown_position] = original option index. Lets us
    # map the guard's chosen shown-position back to the real answer text.
    option_order: Mapped[list] = mapped_column(JSONType, nullable=False)
    # Index of the correct option in the SHUFFLED order shown to the guard.
    correct_option_id: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    attempt: Mapped["QuizAttempt"] = relationship()
