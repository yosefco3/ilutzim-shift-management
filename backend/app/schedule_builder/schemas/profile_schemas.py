"""
Activation profile schemas (part B — schedule builder).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Day-index keys "0".."6" (0=ראשון … 6=שבת) — same vocabulary as Position's
# day_schedules. Kept local so each schema module stays self-contained.
_DAY_LABEL_KEYS = {str(i) for i in range(7)}
_DAY_LABEL_MAX = 50


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
    # Per-day labels. None = leave the stored map untouched; a dict (including {})
    # REPLACES the whole map. Validation [EDGE D4] lives here, not the service.
    day_labels: dict[str, str] | None = None

    @field_validator("day_labels")
    @classmethod
    def _check_day_labels(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        # None is the "unchanged" sentinel — pass it straight through.
        if v is None:
            return None
        cleaned: dict[str, str] = {}
        for day, label in v.items():
            if day not in _DAY_LABEL_KEYS:
                raise ValueError("מפתח יום חייב להיות 0..6")
            trimmed = (label or "").strip()
            if len(trimmed) > _DAY_LABEL_MAX:
                raise ValueError("תווית יום חייבת להיות עד 50 תווים")
            # An empty/whitespace-only value clears that day — not an error.
            if trimmed:
                cleaned[day] = trimmed
        return cleaned

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileUpdate":
        if (
            self.name is None
            and self.kind is None
            and self.description is None
            and self.day_labels is None
        ):
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
    # Per-day free-text labels (day index "0".."6" -> label); {} = none.
    day_labels: dict[str, str]
    is_default: bool
    # Permanent base template (seeded "שגרה"); can never be deleted. The admin UI
    # hides the delete button when true.
    is_base: bool = False
    display_order: int
    created_at: datetime
    # Number of positions owned by this profile. Populated by the repository on
    # list queries; defaults to 0 on paths that don't compute it.
    position_count: int = 0
