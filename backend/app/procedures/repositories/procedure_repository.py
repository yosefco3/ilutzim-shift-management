"""
ProcedureRepository — data access for Procedure rows.
"""

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.procedures.constants import ProcedureStatus
from app.procedures.models.procedure import Procedure
from app.repositories.base_repository import BaseRepository


class ProcedureRepository(BaseRepository[Procedure]):
    """Data-access operations for Procedure."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Procedure)

    async def list_all(self) -> list[Procedure]:
        """All procedures, newest first."""
        stmt = select(Procedure).order_by(desc(Procedure.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_questions(self, id: uuid.UUID) -> Procedure | None:
        """One procedure with its questions eager-loaded (ordered)."""
        stmt = (
            select(Procedure)
            .options(selectinload(Procedure.questions))
            .where(Procedure.id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_published(self) -> list[Procedure]:
        """Published procedures, newest-first (the bot menu/archive)."""
        stmt = (
            select(Procedure)
            .where(Procedure.status == ProcedureStatus.PUBLISHED)
            .order_by(desc(Procedure.published_at), desc(Procedure.created_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_default(self) -> Procedure | None:
        """The single default procedure (הנוהל הנוכחי), or None if there isn't one.

        The partial unique index guarantees at most one row with
        ``is_default=true``.
        """
        stmt = select(Procedure).where(Procedure.is_default.is_(True))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def set_as_default(self, procedure_id: uuid.UUID) -> Procedure:
        """Atomically make ``procedure_id`` the single default procedure.

        Clears any OTHER procedure currently flagged default (the partial unique
        index guarantees at most one), then flags this one. Done via ORM on two
        separate flushes so (a) the identity map stays consistent for callers
        that hold procedure instances, and (b) the clears are guaranteed to land
        BEFORE the new default is set — the partial unique index never sees two
        rows with ``is_default=true`` at once.
        """
        others = (
            await self.session.execute(
                select(Procedure).where(
                    Procedure.is_default.is_(True),
                    Procedure.id != procedure_id,
                )
            )
        ).scalars().all()
        for other in others:
            other.is_default = False
        await self.session.flush()  # land the clears first

        proc = await self.get_by_id(procedure_id)
        if proc is None:
            raise ValueError(f"Procedure with id={procedure_id} not found")
        proc.is_default = True
        await self.session.flush()  # then the new default
        return proc
