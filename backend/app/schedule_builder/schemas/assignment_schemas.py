"""
Assignment schemas (part B — task 05, manual assignment).

Read/write payloads for filling board cells and the assignable-guard pool.
"""

import uuid

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class _SegmentValidatorsMixin(BaseModel):
    """Shared validation for a cell assignment's optional time segment.

    Single source of truth applied to BOTH the create payload and the segment
    update (B-5 — the create path previously had NO segment validation, so a
    ``"7pm"`` slipped through and later crashed export/pool at 500):
      - each of ``segment_start`` / ``segment_end`` is a well-formed ``HH:MM``;
      - both are set or both are null (null/null = the whole window);
      - a degenerate ``segment_start == segment_end`` is rejected — the backend's
        ``intervals.normalize`` reads ``s == e`` as a full 24h day, which is not
        the admin's intent (whole-window is null/null, not equal endpoints).
    """
    segment_start: str | None = None
    segment_end: str | None = None

    @field_validator("segment_start", "segment_end")
    @classmethod
    def _hhmm(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) != 2 or len(v) != 5:
            raise ValueError("segment must be 'HH:MM'")
        hh, mm = parts
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError("segment must be 'HH:MM'")
        return v

    @model_validator(mode="after")
    def _both_or_neither(self):
        if (self.segment_start is None) != (self.segment_end is None):
            raise ValueError("segment_start and segment_end must both be set or both null")
        if (
            self.segment_start is not None
            and self.segment_start == self.segment_end
        ):
            raise ValueError("segment_start and segment_end must differ")
        return self


class AssignmentCreate(_SegmentValidatorsMixin):
    """Payload to place a guard on a cell (segment optional = whole window)."""
    position_id: uuid.UUID
    day_index: int
    user_id: uuid.UUID

    @field_validator("day_index")
    @classmethod
    def _day_in_range(cls, v: int) -> int:
        if not 0 <= v <= 6:
            raise ValueError("day_index must be 0..6")
        return v


class AssignmentSegmentUpdate(_SegmentValidatorsMixin):
    """Set/clear an assignment's time segment (null/null = whole window).

    The split geometry is computed on the frontend; the backend only stores and
    lightly validates (HH:MM format, both-or-neither, non-degenerate), matching
    the deliberately thin validation in AssignmentService.
    """


class AssignmentResponse(BaseModel):
    """One placed assignment, with the guard's display name + attributes."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    position_id: uuid.UUID
    day_index: int
    user_id: uuid.UUID
    user_full_name: str
    user_roles: list[str]
    segment_start: str | None = None
    segment_end: str | None = None

    @classmethod
    def from_orm_with_guard(cls, a) -> "AssignmentResponse":
        """Build from a ScheduleAssignment whose ``user`` is eager-loaded."""
        return cls(
            id=a.id,
            position_id=a.position_id,
            day_index=a.day_index,
            user_id=a.user_id,
            user_full_name=a.user.full_name,
            user_roles=list(a.user.roles or []),
            segment_start=a.segment_start,
            segment_end=a.segment_end,
        )


class PoolWindowSchema(BaseModel):
    """A merged availability window 'HH:MM'→'HH:MM' (security-day axis)."""
    start: str
    end: str


class PoolGuardSchema(BaseModel):
    """One assignable guard with availability, remaining hours and notes."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    roles: list[str]
    notes: str | None = None
    # Per-day index ("0".."6") → merged availability windows.
    availability: dict[str, list[PoolWindowSchema]] = {}
    available_hours: float = 0.0
    assigned_hours: float = 0.0
    remaining_hours: float = 0.0
