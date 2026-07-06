"""
Shared declarative base and common model columns.
"""

import re
import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Root declarative base for all models."""
    pass


class BaseModel(Base):
    """Abstract base model with UUID PK and auto-timestamps."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Auto-generate table name: User -> users, DailyStatus -> daily_statuses."""
        name = cls.__name__
        # Insert underscore before uppercase letters, then lowercase
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        # Words ending with 's' get 'es' (status → statuses)
        if snake.endswith("s"):
            return f"{snake}es"
        return f"{snake}s"
