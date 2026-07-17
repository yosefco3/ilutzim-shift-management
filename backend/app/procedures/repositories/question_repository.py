"""
QuizQuestionRepository — data access for the question bank.

The bank is append + disable-after-publish: a question can be deleted only while
the procedure is still a DRAFT, and regeneration deletes only the
``source=AI AND edited_at IS NULL`` rows (admin edits + manual questions are
preserved). See ``QuizQuestionService`` for those rules.
"""

import uuid

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.procedures.constants import QuestionSource
from app.procedures.models.quiz_question import QuizQuestion
from app.repositories.base_repository import BaseRepository


class QuizQuestionRepository(BaseRepository[QuizQuestion]):
    """Data-access operations for QuizQuestion."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuizQuestion)

    async def list_for_procedure(self, procedure_id: uuid.UUID) -> list[QuizQuestion]:
        """All questions for a procedure, in display order."""
        stmt = (
            select(QuizQuestion)
            .where(QuizQuestion.procedure_id == procedure_id)
            .order_by(QuizQuestion.display_order, QuizQuestion.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self, procedure_id: uuid.UUID) -> list[QuizQuestion]:
        """Active questions for a procedure, in display order (the sampling pool)."""
        stmt = (
            select(QuizQuestion)
            .where(
                QuizQuestion.procedure_id == procedure_id,
                QuizQuestion.is_active.is_(True),
            )
            .order_by(QuizQuestion.display_order, QuizQuestion.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, procedure_id: uuid.UUID) -> int:
        """Number of active questions for a procedure."""
        stmt = select(func.count()).select_from(QuizQuestion).where(
            QuizQuestion.procedure_id == procedure_id,
            QuizQuestion.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def count_all(self, procedure_id: uuid.UUID) -> int:
        """Total questions for a procedure (active + disabled)."""
        stmt = select(func.count()).select_from(QuizQuestion).where(
            QuizQuestion.procedure_id == procedure_id
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def next_display_order(self, procedure_id: uuid.UUID) -> int:
        """The next display_order value (max + 1, or 0)."""
        stmt = select(func.max(QuizQuestion.display_order)).where(
            QuizQuestion.procedure_id == procedure_id
        )
        result = await self.session.execute(stmt)
        current = result.scalar()
        return (current or 0) + 1

    async def delete_regenerable(self, procedure_id: uuid.UUID) -> int:
        """Delete AI questions that were never admin-edited.

        Regeneration deletes ONLY ``source=AI AND edited_at IS NULL`` — admin
        edits (edited_at set) and manual questions (source=MANUAL) survive.
        Returns the number of rows deleted.
        """
        stmt = sa_delete(QuizQuestion).where(
            QuizQuestion.procedure_id == procedure_id,
            QuizQuestion.source == QuestionSource.AI,
            QuizQuestion.edited_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)
