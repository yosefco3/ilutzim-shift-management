"""
Requirement-attribute schemas (part B — schedule builder).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


class AttributeCreate(BaseModel):
    """Schema for creating a requirement attribute."""
    key: str = Field(min_length=1, max_length=50, pattern=_KEY_PATTERN)
    label: str = Field(min_length=1, max_length=100)


class AttributeUpdate(BaseModel):
    """Schema for updating a requirement attribute. At least one field required."""
    key: str | None = Field(default=None, min_length=1, max_length=50, pattern=_KEY_PATTERN)
    label: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "AttributeUpdate":
        if self.key is None and self.label is None:
            raise ValueError("יש לספק לפחות שדה אחד לעדכון")
        return self


class AttributeResponse(BaseModel):
    """Schema for requirement-attribute data in API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    label: str
    display_order: int
    created_at: datetime
