"""
Board schemas (part B — task 04 board skeleton).

Read-only positions × days grid for a week, plus the week↔profile assignment
read/write payloads.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class WindowSchema(BaseModel):
    """A time window 'HH:MM'→'HH:MM' (end<=start wraps past midnight)."""
    start: str
    end: str


class BoardCellSchema(BaseModel):
    """One position×day cell."""
    day_index: int
    active: bool
    window: WindowSchema | None = None
    is_override: bool = False


class BoardRowSchema(BaseModel):
    """One position row with its 7 per-day cells."""
    position_id: uuid.UUID
    name: str
    band: str  # "morning" | "evening" | "night"
    canonical_window: WindowSchema | None
    required_attributes: list[str]
    # Event / non-splitting position — guards share the whole window, no tiling.
    is_event: bool = False
    # Event-only fixed participant count — the cell tiles into this many slots;
    # None = unlimited. Drives the "missing guard" slots + understaffed warning.
    event_required_count: int | None = None
    active_day_count: int
    cells: list[BoardCellSchema]


class BoardDaySchema(BaseModel):
    """A day column header: index 0=ראשון … 6=שבת + its ISO date."""
    index: int
    date: str


class BoardWeekSchema(BaseModel):
    """Week meta for the board header."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    start_date: date
    end_date: date
    status: str


class BoardProfileSchema(BaseModel):
    """Effective profile meta for the board header."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    is_default: bool


class BoardResponse(BaseModel):
    """The full resolved board."""
    week: BoardWeekSchema
    profile: BoardProfileSchema
    is_default_fallback: bool
    days: list[BoardDaySchema]
    rows: list[BoardRowSchema]


class WeekProfileResponse(BaseModel):
    """The profile a week is built from (effective)."""
    profile: BoardProfileSchema
    is_default_fallback: bool


class WeekProfileAssign(BaseModel):
    """Payload to bind a week to a profile."""
    profile_id: uuid.UUID
