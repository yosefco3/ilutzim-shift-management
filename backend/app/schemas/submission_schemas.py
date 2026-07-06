"""Submission schemas — core shift/availability validation."""

import uuid
from datetime import date, datetime, time

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.constants import ShiftType, SubmissionStatus
from app.messages import Messages


# ── Guard-side (Telegram WebApp) schemas ────────────────────────────────────

class GuardShiftInput(BaseModel):
    """Single shift as submitted by a guard — raw time strings."""
    shift_type: ShiftType
    from_hour: str | None = None  # "HH:MM"
    to_hour: str | None = None    # "HH:MM"


class GuardDayInput(BaseModel):
    """Single day entry in a guard's weekly submission."""
    day_index: int = Field(ge=0, le=6)
    shifts: list[GuardShiftInput] = []


class GuardSubmissionRequest(BaseModel):
    """Payload sent by the guard's frontend via POST /submissions."""
    week_id: uuid.UUID
    general_notes: str | None = None
    days: list[GuardDayInput]

    @model_validator(mode="after")
    def validate_days_not_empty(self) -> "GuardSubmissionRequest":
        if len(self.days) == 0:
            raise ValueError(Messages.VAL_EMPTY_DAYS)
        return self


class AdminSubmissionRequest(GuardSubmissionRequest):
    """Payload sent by an admin filling constraints on behalf of a guard.

    Same shape as a guard submission, plus the target ``user_id`` (the admin
    is authenticated separately, so the guard is identified explicitly).
    """
    user_id: uuid.UUID


# ── Internal schemas (used by service layer) ─────────────────────────────────

class ShiftWindowInput(BaseModel):
    """Schema for a single shift window within a day."""
    shift_type: ShiftType
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_times(self) -> "ShiftWindowInput":
        if self.start_time == self.end_time:
            raise ValueError(Messages.VAL_SAME_START_END)
        if self.shift_type == ShiftType.NIGHT:
            pass  # Night shifts can cross midnight
        elif self.start_time > self.end_time:
            raise ValueError(Messages.VAL_SAME_START_END)
        return self


class DayStatusInput(BaseModel):
    """Schema for a single day's availability and shifts."""
    date: date
    is_available: bool
    shifts: list[ShiftWindowInput] = []

    @model_validator(mode="after")
    def validate_shifts_availability(self) -> "DayStatusInput":
        if not self.is_available and len(self.shifts) > 0:
            raise ValueError(Messages.VAL_UNAVAILABLE_WITH_SHIFTS)
        if self.is_available and len(self.shifts) == 0:
            raise ValueError(Messages.VAL_AVAILABLE_NO_SHIFTS)
        return self


class SubmissionCreate(BaseModel):
    """Schema for creating/updating a weekly submission."""
    week_id: uuid.UUID
    user_id: uuid.UUID
    general_notes: str | None = None
    days: list[DayStatusInput]

    @model_validator(mode="after")
    def validate_days_not_empty(self) -> "SubmissionCreate":
        if len(self.days) == 0:
            raise ValueError(Messages.VAL_EMPTY_DAYS)
        return self


# ── Response schemas ─────────────────────────────────────────────────────────

class ShiftWindowResponse(BaseModel):
    """Schema for shift window in API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shift_type: ShiftType
    start_time: time
    end_time: time


class DayStatusResponse(BaseModel):
    """Schema for day status in API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    is_available: bool
    shift_windows: list[ShiftWindowResponse] = []


class SubmissionResponse(BaseModel):
    """Schema for submission data in API responses."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    user_id: uuid.UUID
    week_id: uuid.UUID
    general_notes: str | None = None
    submitted_at: datetime
    # True once an admin has acknowledged this submission's rule violations.
    violation_acknowledged: bool = False
    # ORM exposes the relation as ``daily_statuses``; the API contract is ``days``.
    days: list[DayStatusResponse] = Field(
        default_factory=list,
        validation_alias=AliasChoices("daily_statuses", "days"),
    )


class SubmissionStatusGrid(BaseModel):
    """Grid row showing a user's submission status for a week."""
    user_id: uuid.UUID
    full_name: str
    phone_number: str
    submitted_at: datetime | None = None
    is_active: bool = True
    # False when the guard has never linked Telegram (admin fills their
    # constraints by hand and their schedule can't be delivered over the bot).
    has_telegram: bool = True


class MissingGuardInfo(BaseModel):
    """Info about a guard who hasn't submitted."""
    user_id: str
    full_name: str
    phone_number: str


class SubmissionWithName(SubmissionResponse):
    """Submission response with the guard's full name included."""
    full_name: str


class WeekSubmissionsDetailed(BaseModel):
    """Full submission details for a week."""
    submitted: list[SubmissionWithName]
    missing: list[MissingGuardInfo]
    week_label: str


class AcknowledgeViolationRequest(BaseModel):
    """Admin toggle for acknowledging a submission's rule violations."""
    acknowledged: bool = True


class DeviationDetail(BaseModel):
    """Detail of a single deviation rule violation."""
    rule_name: str
    required: int
    actual: int
