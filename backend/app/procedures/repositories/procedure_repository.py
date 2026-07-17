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
