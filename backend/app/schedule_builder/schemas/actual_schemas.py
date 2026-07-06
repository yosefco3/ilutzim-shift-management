"""
Actual-schedule schemas (steps 05–06) — the editable execution board.

Mirrors the builder's assignment/board payloads, re-pointed at the actual
layer (``actual_position_id`` instead of ``position_id``) and extended with
what only exists here: the ad-hoc marker, seed metadata and soft warnings.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schedule_builder.schemas.assignment_schemas import _SegmentValidatorsMixin
from app.schedule_builder.schemas.board_schemas import (
    BoardDaySchema,
    BoardWeekSchema,
    WindowSchema,
)
from app.schedule_builder.schemas.position_schemas import (
    _validate_day_schedules,
    _validate_required_attributes,
)


class ActualAssignmentCreate(_SegmentValidatorsMixin):
    """Place a guard on an actual cell (segment optional = whole window)."""

    actual_position_id: uuid.UUID
    day_index: int
    user_id: uuid.UUID

    @field_validator("day_index")
    @classmethod
    def _day_in_range(cls, v: int) -> int:
        if not 0 <= v <= 6:
            raise ValueError("day_index must be 0..6")
        return v


class ActualSegmentUpdate(_SegmentValidatorsMixin):
    """Set/clear an actual assignment's segment (null/null = whole window)."""


class ActualAssignmentResponse(BaseModel):
    """One placed actual assignment, with the guard's display fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actual_position_id: uuid.UUID
    day_index: int
    user_id: uuid.UUID
    user_full_name: str
    user_roles: list[str]
    segment_start: str | None = None
    segment_end: str | None = None

    @classmethod
    def from_orm_with_guard(cls, a) -> "ActualAssignmentResponse":
        """Build from an ActualAssignment whose ``user`` is eager-loaded."""
        return cls(
            id=a.id,
            actual_position_id=a.actual_position_id,
            day_index=a.day_index,
            user_id=a.user_id,
            user_full_name=a.user.full_name,
            user_roles=list(a.user.roles or []),
            segment_start=a.segment_start,
            segment_end=a.segment_end,
        )


class ActualPositionCreate(BaseModel):
    """Add an ad-hoc position mid-week (free-form, not tied to any profile)."""

    name: str = Field(min_length=1, max_length=255)
    day_schedules: dict = Field(default_factory=dict)
    # Informational on the actual board (free editing enforces nothing) — kept
    # for display parity with the shared position form.
    required_attributes: list[str] = Field(default_factory=list)
    is_event: bool = False
    event_required_count: int | None = Field(default=None, ge=1)

    @field_validator("day_schedules")
    @classmethod
    def _check_schedules(cls, v: dict) -> dict:
        return _validate_day_schedules(v)

    @field_validator("required_attributes")
    @classmethod
    def _check_attrs(cls, v: list) -> list:
        return _validate_required_attributes(v)


class ActualPositionUpdate(BaseModel):
    """Edit an actual position. Only provided fields change."""

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


class ActualPositionResponse(BaseModel):
    """One actual position row (flat — the board GET returns the full grid)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    day_schedules: dict
    display_order: int
    is_event: bool
    event_required_count: int | None = None
    source_position_id: uuid.UUID | None = None


class SaveAsProfileRequest(BaseModel):
    """Promote the week's actual board to a new reusable profile."""

    name: str = Field(min_length=1, max_length=255)


class SaveAsProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ActualBoardRowSchema(BaseModel):
    """One actual-board position row with its 7 per-day cells."""

    position_id: uuid.UUID  # the ActualPosition id
    name: str
    band: str  # "morning" | "evening" | "night"
    canonical_window: WindowSchema | None
    required_attributes: list[str]
    is_event: bool = False
    event_required_count: int | None = None
    active_day_count: int
    cells: list[dict]
    # Actual-only: where the row came from. is_adhoc=True marks a position
    # added mid-week (no planned source).
    source_position_id: uuid.UUID | None = None
    is_adhoc: bool = False


class ReinforcementCreate(BaseModel):
    """Create a one-off external reinforcement (מתגבר) for this week."""

    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    phone_number: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    # The external supervisor responsible for the helper (surfaces in the
    # reinforcements report).
    supervisor_name: str | None = Field(default=None, max_length=100)


class ReinforcementResponse(BaseModel):
    """One reinforcement card, with its guard's display fields."""

    id: uuid.UUID  # the card id (used for deletion)
    user_id: uuid.UUID  # what assignments reference
    full_name: str
    phone_number: str | None = None
    note: str | None = None
    supervisor_name: str | None = None

    @classmethod
    def from_card(cls, card) -> "ReinforcementResponse":
        """Build from an ActualReinforcement whose ``user`` is eager-loaded."""
        phone = card.user.phone_number
        return cls(
            id=card.id,
            user_id=card.user_id,
            full_name=card.user.full_name,
            # The auto-generated placeholder is an internal detail, not a phone.
            phone_number=None if (phone or "").startswith("EXT-") else phone,
            note=card.user.exemptions_notes,
            supervisor_name=card.supervisor_name,
        )


class ActualBoardResponse(BaseModel):
    """The full actual board: rows + assignments + reinforcements + warnings."""

    week: BoardWeekSchema
    actual_schedule_id: uuid.UUID
    seeded_at: datetime
    seed_source: str
    days: list[BoardDaySchema]
    rows: list[ActualBoardRowSchema]
    assignments: list[ActualAssignmentResponse]
    # This week's reinforcement cards (מתגברים) — external one-off helpers.
    reinforcements: list[ReinforcementResponse] = []
    # Soft advisories (already_in_shift / overstaffed_cell /
    # assignments_outside_window) — informational, never blocking.
    warnings: list[dict]
