"""
AttributeRepository — data access for requirement attributes (part B).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import BaseRepository
from app.schedule_builder.models.requirement_attribute import RequirementAttribute


class AttributeRepository(BaseRepository[RequirementAttribute]):
    """Data-access operations for RequirementAttribute entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RequirementAttribute)

    async def get_all_ordered(self) -> list[RequirementAttribute]:
        """Return all attributes ordered by display_order, then created_at."""
        stmt = select(self.model_class).order_by(
            RequirementAttribute.display_order.asc(),
            RequirementAttribute.created_at.asc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, key: str) -> RequirementAttribute | None:
        """Return the attribute with the given key, if any."""
        stmt = select(self.model_class).where(RequirementAttribute.key == key)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count(self) -> int:
        """Return the total number of attributes."""
        result = await self.session.execute(
            select(func.count(RequirementAttribute.id))
        )
        return result.scalar()

    async def max_display_order(self) -> int:
        """Return the highest display_order in use (0 if none)."""
        result = await self.session.execute(
            select(func.coalesce(func.max(RequirementAttribute.display_order), 0))
        )
        return result.scalar() or 0
