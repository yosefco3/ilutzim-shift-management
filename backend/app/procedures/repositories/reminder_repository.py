"""
ProcedureReminderRepository — the one-reminder-per-guard ledger.

The unique (procedure_id, user_id) constraint makes the reminder job idempotent:
re-runs can't duplicate a reminder. ``record_or_skip`` writes a row only if none
exists yet and returns whether it wrote (the caller sends the reminder only then).
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.procedures.models.procedure_reminder_sent import ProcedureReminderSent
from app.repositories.base_repository import BaseRepository


class ProcedureReminderRepository(BaseRepository[ProcedureReminderSent]):
    """Data-access operations for ProcedureReminderSent."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ProcedureReminderSent)

    async def exists(
        self, procedure_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Whether a reminder was already recorded for this procedure+user."""
        stmt = select(ProcedureReminderSent.id).where(
            ProcedureReminderSent.procedure_id == procedure_id,
            ProcedureReminderSent.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def record_or_skip(
        self, procedure_id: uuid.UUID, user_id: uuid.UUID, sent_at: datetime
    ) -> bool:
        """Record a reminder if not already sent. Returns True if written.

        Idempotent: a second call for the same (procedure, user) is a no-op.
        The unique constraint is the final guard, but the EXISTS check avoids
        unnecessary write attempts on the common repeated-job path.
        """
        if await self.exists(procedure_id, user_id):
            return False
        self.session.add(
            ProcedureReminderSent(
                procedure_id=procedure_id, user_id=user_id, sent_at=sent_at
            )
        )
        await self.session.flush()
        return True
