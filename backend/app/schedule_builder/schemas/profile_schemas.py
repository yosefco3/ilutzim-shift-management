"""
Activation profile schemas (part B — schedule builder).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProfileCreate(BaseModel):
    """Schema for creating an activation profile."""
    name: str = Field(min_length=1, max_length=255)
    kind: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class ProfileUpdate(BaseModel):
    """Schema for renaming / updating profile meta. At least one field required."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileUpdate":
        if self.name is None and self.kind is None and self.description is None:
            raise ValueError("יש לספק לפחות שדה אחד לעדכון")
        return self


class ProfileDuplicate(BaseModel):
    """Schema for duplicating a profile (optional new name)."""
    new_name: str | None = Field(default=None, min_length=1, max_length=255)


class ProfileResponse(BaseModel):
    """Schema for activation profile data in API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str | None
    description: str | None
    is_default: bool
    display_order: int
    created_at: datetime
    # Number of positions owned by this profile. Populated by the repository on
    # list queries; defaults to 0 on paths that don't compute it.
    position_count: int = 0
