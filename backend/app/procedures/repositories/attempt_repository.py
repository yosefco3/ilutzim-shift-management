"""
QuizAttemptRepository — data access for scored quiz attempts.

The partial unique index guarantees at most one IN_PROGRESS attempt per
(user, procedure); the service handles the resulting IntegrityError on a race.
"""

import uuid

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.procedures.constants import AttemptStatus
from app.procedures.models.quiz_attempt import QuizAttempt
from app.repositories.base_repository import BaseRepository


class QuizAttemptRepository(BaseRepository[QuizAttempt]):
    """Data-access operations for QuizAttempt."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuizAttempt)

    async def get_in_progress(
        self, user_id: uuid.UUID, procedure_id: uuid.UUID
    ) -> QuizAttempt | None:
        """The user's current IN_PROGRESS attempt for a procedure, if any."""
        stmt = select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.procedure_id == procedure_id,
            QuizAttempt.status == AttemptStatus.IN_PROGRESS,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_any_in_progress(self, user_id: uuid.UUID) -> QuizAttempt | None:
        """The user's current IN_PROGRESS attempt across ALL procedures, if any.

        One quiz at a time: a start on procedure B is refused while an attempt
        on procedure A is open (the guard exits or finishes it first).
        """
        stmt = (
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.status == AttemptStatus.IN_PROGRESS,
            )
            .order_by(QuizAttempt.started_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def abandon_all_in_progress(self, user_id: uuid.UUID) -> int:
        """Flip ALL of the user's IN_PROGRESS attempts to ABANDONED (quiz exit).

        Returns the count flipped (0 → the guard had no open quiz). Late poll
        answers for an abandoned attempt are ignored by ``record_answer``.
        """
        stmt = (
            sa_update(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.status == AttemptStatus.IN_PROGRESS,
            )
            .values(status=AttemptStatus.ABANDONED)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def abandon_in_progress(
        self, user_id: uuid.UUID, procedure_id: uuid.UUID
    ) -> int:
        """Flip any IN_PROGRESS attempt for (user, procedure) to ABANDONED.

        Called at the start of a new attempt so a stale in-flight attempt (the
        guard walked away mid-quiz) is superseded. Returns the count flipped.
        """
        stmt = (
            sa_update(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.procedure_id == procedure_id,
                QuizAttempt.status == AttemptStatus.IN_PROGRESS,
            )
            .values(status=AttemptStatus.ABANDONED)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def list_for_user_procedure(
        self, user_id: uuid.UUID, procedure_id: uuid.UUID
    ) -> list[QuizAttempt]:
        """All of a user's attempts for one procedure (results aggregation)."""
        stmt = (
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.procedure_id == procedure_id,
            )
            .order_by(QuizAttempt.started_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_procedure(self, procedure_id: uuid.UUID) -> list[QuizAttempt]:
        """All attempts for a procedure (results aggregation)."""
        stmt = (
            select(QuizAttempt)
            .where(QuizAttempt.procedure_id == procedure_id)
            .order_by(QuizAttempt.user_id, QuizAttempt.started_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def has_passed(
        self, user_id: uuid.UUID, procedure_id: uuid.UUID
    ) -> bool:
        """Whether the user has any passed attempt for the procedure."""
        stmt = select(func.count()).select_from(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.procedure_id == procedure_id,
            QuizAttempt.passed.is_(True),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0) > 0
