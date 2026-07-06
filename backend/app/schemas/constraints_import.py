"""Response schemas for the constraints-import preview / commit endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ShiftCellsOut(BaseModel):
    """Per-shift display text for a day (None = unavailable/empty)."""
    morning: str | None = None
    afternoon: str | None = None
    night: str | None = None


class DayPreview(BaseModel):
    day_index: int          # 0 = ראשון … 6 = שבת
    day_name: str
    segments: list[str]     # merged union windows, e.g. ["07:00–19:00"]
    hours: float            # union hours for the day
    shifts: ShiftCellsOut


class GuardPreview(BaseModel):
    id: str | None = None   # the guard's DB id carried in the file's "מזהה" column
    name: str
    exists: bool            # informational only: this guard (by id or name) already exists
    notes: str | None = None
    roles: list[str] = []   # attributes lifted out of notes, e.g. ["AHMASH", "PATROL_VEHICLE"]
    weekly_hours: float
    days: list[DayPreview]


class ConstraintsPreviewResponse(BaseModel):
    week_start: date | None = None
    week_end: date | None = None
    guards: list[GuardPreview]
    errors: list[str]


class ImportSummary(BaseModel):
    """Structured summary returned after a commit (step 04/05)."""
    week_start: date | None = None
    week_end: date | None = None
    imported: int           # guards written successfully
    created_new: int        # guards that did not exist before and were created
    errors: list[str]


class ConstraintsCommitResponse(BaseModel):
    summary: ImportSummary
    guards: list[GuardPreview]
