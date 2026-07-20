"""
Position schemas (part B — schedule builder).

Input validation for positions lives HERE — most importantly the shape of
``day_schedules`` (the per-day hours map). ``end <= start`` is allowed (a night
window wraps past midnight, the part-A convention).
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DAY_KEYS = {str(i) for i in range(7)}  # "0".."6", 0=ראשון … 6=שבת


class DaySchedule(BaseModel):
    """Hours for a single active day."""
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("שעה חייבת להיות בפורמט HH:MM")
        return v


def _validate_day_schedules(value: dict, *, require_non_empty: bool = True) -> dict:
    """Validate the ``day_schedules`` map: keys must be "0".."6", each value a
    valid ``DaySchedule`` (``HH:MM`` start/end — the part-A convention, where
    ``end <= start`` is a valid overnight wrap).

    ``require_non_empty=False`` permits an empty ``{}`` — the matrix editor can
    close a position for the whole week [EDGE D3]. The single-position create /
    update schemas keep the default (≥1 active day).
    """
    if not isinstance(value, dict) or (require_non_empty and not value):
        raise ValueError("יש להגדיר לפחות יום פעיל אחד")
    for day, hours in value.items():
        if day not in _DAY_KEYS:
            raise ValueError("מפתח יום חייב להיות 0..6")
        DaySchedule.model_validate(hours)
    return value


def _validate_required_attributes(value: list) -> list:
    """A list of unique non-empty attribute keys."""
    if len(set(value)) != len(value):
        raise ValueError("דרישות חייבות להיות ייחודיות")
    return value


class PositionCreate(BaseModel):
    """Schema for creating a position (profile_id comes from the path)."""
    name: str = Field(min_length=1, max_length=255)
    day_schedules: dict = Field(default_factory=dict)
    required_attributes: list[str] = Field(default_factory=list)
    # Event / non-splitting position: guards attend the same window together.
    is_event: bool = False
    # Event-only fixed participant count (>=1). None = unlimited. Ignored (forced
    # to None) by the service when is_event is False.
    event_required_count: int | None = Field(default=None, ge=1)

    @field_validator("day_schedules")
    @classmethod
    def _check_schedules(cls, v: dict) -> dict:
        return _validate_day_schedules(v)

    @field_validator("required_attributes")
    @classmethod
    def _check_attrs(cls, v: list) -> list:
        return _validate_required_attributes(v)


class PositionUpdate(BaseModel):
    """Schema for updating a position. At least one field required."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    day_schedules: dict | None = None
    required_attributes: list[str] | None = None
    is_event: bool | None = None
    event_required_count: int | None = Field(default=None, ge=1)

    @field_validator("day_schedules")
    @classmethod
    def _check_schedules(cls, v: dict | None) -> dict | None:
        return v if v is None else _validate_day_schedules(v)

    @field_validator("required_attributes")
    @classmethod
    def _check_attrs(cls, v: list | None) -> list | None:
        return v if v is None else _validate_required_attributes(v)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "PositionUpdate":
        if (
            self.name is None
            and self.day_schedules is None
            and self.required_attributes is None
            and self.is_event is None
            and self.event_required_count is None
        ):
            raise ValueError("יש לספק לפחות שדה אחד לעדכון")
        return self


class PositionCopy(BaseModel):
    """Schema for copying a position into another profile (source id from path)."""
    target_profile_id: uuid.UUID


class PositionReorder(BaseModel):
    """Schema for reordering a profile's positions (drag-and-drop on the board).

    ``position_ids`` must be an exact permutation of the profile's positions —
    the service assigns ``display_order`` by list index.
    """
    position_ids: list[uuid.UUID] = Field(min_length=1)

    @field_validator("position_ids")
    @classmethod
    def _no_duplicates(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("מזהי עמדות חייבים להיות ייחודיים")
        return v


class PositionDayScheduleItem(BaseModel):
    """One row of a bulk day-schedules update: which position, and its full
    ``day_schedules`` map. Empty ``{}`` is valid (the position is closed all
    week) [EDGE D3]; day keys and ``HH:MM`` reuse the single-position rules.
    """
    position_id: uuid.UUID
    day_schedules: dict = Field(default_factory=dict)

    @field_validator("day_schedules")
    @classmethod
    def _check_schedules(cls, v: dict) -> dict:
        return _validate_day_schedules(v, require_non_empty=False)


class PositionsBulkDaySchedules(BaseModel):
    """Body for the atomic bulk day-schedules PUT.

    Duplicate ``position_id`` across items is NOT rejected here — the service
    treats it as a 409 mismatch (with the offending ids), not a 422 schema
    error, mirroring the unknown / foreign-id case [EDGE C2]. Empty items → 422.
    """
    items: list[PositionDayScheduleItem] = Field(min_length=1)


class PositionResponse(BaseModel):
    """Schema for position data in API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    day_schedules: dict
    required_attributes: list[str]
    is_event: bool
    event_required_count: int | None = None
    display_order: int
    created_at: datetime
