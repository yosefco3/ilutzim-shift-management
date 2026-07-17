"""
QuizPollLinkRepository — maps a Telegram quiz poll id back to its attempt+question.

``telegram_poll_id`` is the primary key; ``get_by_id`` (from BaseRepository)
looks up by that string PK.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.procedures.models.quiz_poll_link import QuizPollLink
from app.repositories.base_repository import BaseRepository


class QuizPollLinkRepository(BaseRepository[QuizPollLink]):
    """Data-access operations for QuizPollLink."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuizPollLink)

    async def get(self, telegram_poll_id: str) -> QuizPollLink | None:
        """Look up a poll link by its Telegram poll id."""
        return await self.get_by_id(telegram_poll_id)

    async def get_for_attempt_question(
        self, attempt_id: uuid.UUID, question_id: uuid.UUID
    ) -> QuizPollLink | None:
        """The poll link for a specific attempt+question (race / outstanding check)."""
        stmt = select(QuizPollLink).where(
            QuizPollLink.attempt_id == attempt_id,
            QuizPollLink.question_id == question_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
