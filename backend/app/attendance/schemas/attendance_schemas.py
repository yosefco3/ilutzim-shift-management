"""
Attendance API schemas — a 1:1 pydantic mirror of the comparison read-model.

The frontend gets BOTH the raw and the rounded check-out (the UI shows
"15:15 ⤴ בפועל 15:01"), the per-minute segments for the timeline bars, and the
dry summary. No recommendation fields exist anywhere by design.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PlannedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_name: str
    start: datetime
    end: datetime
    is_event: bool = False


class ActualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shift_id: uuid.UUID
    check_in_at: datetime
    check_out_raw: datetime | None = None
    check_out_rounded: datetime | None = None
    status: str
    in_source: str | None = None
    out_source: str | None = None
    out_of_radius: bool = False
    in_event_id: uuid.UUID | None = None
    out_event_id: uuid.UUID | None = None


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start: datetime
    end: datetime
    kind: str


class OrphanOutOut(BaseModel):
    """An OUT punch no shift consumed — exposed with its event id so the
    edit dialog can fix/void it like any paired punch."""

    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    punched_at: datetime
    source: str | None = None


class SummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    planned_minutes: int
    actual_minutes: int
    extra_minutes: int
    delta_in_minutes: int | None = None
    delta_out_minutes: int | None = None
    severity: str
    tag: str
    orphan_out_times: list[str] = Field(default_factory=list)
    orphan_outs: list[OrphanOutOut] = Field(default_factory=list)


class UserDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    user_name: str
    date: date
    band: str
    planned: list[PlannedOut]
    actual: list[ActualOut]
    segments: list[SegmentOut]
    summary: SummaryOut


class BandOut(BaseModel):
    band: str  # morning | evening | night
    rows: list[UserDayOut]


class DayViewOut(BaseModel):
    date: date
    now: datetime
    counters: dict[str, int]
    bands: list[BandOut]


class UserPeriodOut(BaseModel):
    user_id: uuid.UUID
    user_name: str
    date_from: date
    date_to: date
    days: list[UserDayOut]
    summary: dict[str, int]


class StatusOut(BaseModel):
    enabled: bool
    events_today: int
    last_event_at: datetime | None = None


class AdjustmentRequest(BaseModel):
    """One admin correction. Fields beyond ``action``+``reason`` are
    action-specific; the controller validates the combination."""

    action: str  # edit_time | add_punch | void_punch | mark_absence
    reason: str
    event_id: uuid.UUID | None = None       # edit_time / void_punch
    user_id: uuid.UUID | None = None        # add_punch / mark_absence
    work_date: date | None = None           # mark_absence
    direction: str | None = None            # add_punch: in | out
    punched_at: datetime | None = None      # edit_time (new time) / add_punch


class AdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    work_date: date
    action: str
    target_event_id: uuid.UUID | None = None
    before: dict | None = None
    after: dict | None = None
    reason: str
    created_at: datetime


class AdjustmentResult(BaseModel):
    """The recorded correction + the refreshed day for instant UI update."""

    adjustment: AdjustmentOut
    day: UserDayOut


class ManualEntryRequest(BaseModel):
    """Quick manual attendance for a guard (e.g. one without Telegram):
    a check-in and optionally a check-out in one shot. A check-out at or
    before the check-in is interpreted as crossing midnight (night guards)."""

    user_id: uuid.UUID
    date: date
    check_in: str                 # "HH:MM"
    check_out: str | None = None  # "HH:MM" | null (open shift)
    reason: str


class PeriodSummaryRow(BaseModel):
    """One employee's aggregate line for the main page's week/month list."""

    user_id: uuid.UUID
    user_name: str
    planned_minutes: int
    actual_minutes: int
    extra_minutes: int
    days_scheduled: int
    days_present: int
    big: int
    small: int
