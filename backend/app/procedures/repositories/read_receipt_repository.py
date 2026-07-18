"""
ProcedureReadReceiptRepository — the guard "first read" ledger for procedures.

``record_first_read`` is idempotent (``INSERT … ON CONFLICT DO NOTHING``): a
duplicate (procedure, user) row — a double-open, refresh, or revisit — is a
silent no-op that never overwrites the original ``first_read_at``. Recording is
best-effort from the guard GET endpoint: it must never raise and never block the
view (see [EDGE C1]).

``read_map`` returns ``{user_id: first_read_at}`` for a procedure so the results
screen can mark each guard's read state in one query.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.procedures.models.procedure_read_receipt import ProcedureReadReceipt
from app.repositories.base_repository import BaseRepository

# The columns backing the unique ``uq_procedure_read_once`` constraint — the
# ON CONFLICT target for both dialects.
_CONFLICT_TARGET = ["procedure_id", "user_id"]


class ProcedureReadReceiptRepository(BaseRepository[ProcedureReadReceipt]):
    """Data-access operations for ProcedureReadReceipt."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ProcedureReadReceipt)

    @property
    def _dialect_name(self) -> str:
        return self.session.bind.dialect.name

    async def record_first_read(
        self, procedure_id: uuid.UUID, user_id: uuid.UUID, now: datetime
    ) -> None:
        """Record a guard's first-open timestamp, idempotently.

        ``INSERT … ON CONFLICT DO NOTHING`` so a duplicate (procedure, user) is a
        no-op — the original ``first_read_at`` is never overwritten (double-open
        / refresh / revisit all collapse to one row). Best-effort: never raises
        on a conflict. [EDGE C1]
        """
        values = {
            "procedure_id": procedure_id,
            "user_id": user_id,
            "first_read_at": now,
        }
        if self._dialect_name == "sqlite":
            stmt = sqlite_insert(ProcedureReadReceipt).values(**values).on_conflict_do_nothing(
                index_elements=_CONFLICT_TARGET
            )
        else:  # PostgreSQL in prod
            stmt = pg_insert(ProcedureReadReceipt).values(**values).on_conflict_do_nothing(
                index_elements=_CONFLICT_TARGET
            )
        await self.session.execute(stmt)

    async def read_map(
        self, procedure_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime]:
        """``{user_id: first_read_at}`` for every guard who read this procedure."""
        stmt = select(
            ProcedureReadReceipt.user_id, ProcedureReadReceipt.first_read_at
        ).where(ProcedureReadReceipt.procedure_id == procedure_id)
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
