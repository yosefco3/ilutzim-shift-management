"""
Generic base repository with async CRUD operations.
"""

import uuid
from typing import Generic, Type, TypeVar

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BaseModel
from app.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """Generic data-access layer for UUID-based models."""

    def __init__(self, session: AsyncSession, model_class: Type[T]) -> None:
        self.session = session
        self.model_class = model_class

    async def get_by_id(self, id: uuid.UUID) -> T | None:
        """Retrieve a single record by primary key."""
        result = await self.session.get(self.model_class, id)
        return result

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[T]:
        """Return a paginated list of all records."""
        stmt = select(self.model_class).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> T:
        """Create a new record and return it."""
        instance = self.model_class(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        logger.debug("Created %s record", self.model_class.__name__)
        return instance

    async def update(self, id: uuid.UUID, **kwargs) -> T:
        """Update a record by ID with the given fields."""
        instance = await self.get_by_id(id)
        if instance is None:
            raise ValueError(f"{self.model_class.__name__} with id={id} not found")
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        logger.debug("Updated %s %s", self.model_class.__name__, id)
        return instance

    async def delete(self, id: uuid.UUID) -> bool:
        """Delete a record by ID. Returns True if deleted."""
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        logger.debug("Deleted %s %s", self.model_class.__name__, id)
        return True

    async def save(self, instance: T) -> T:
        """Add (or merge), flush, and refresh an instance."""
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance