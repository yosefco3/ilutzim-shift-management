"""Union-merge of availability windows and union-based hour counting.

The locked rule (see ``STAGE_B_PROMPTS/README.md`` → "חפיפות = איחוד"):

    overlapping/touching windows are **merged**, and free hours are measured
    from the merged union — **not** summed per window:

        07:00–16:30 (morning) ∪ 15:00–19:00 (evening) = 07:00–19:00 = 12h (not 13.5)

This module is **pure** (no DB). A day is reduced to a minimal list of
``Segment`` (minutes-from-midnight, ``end`` exclusive). Night windows that wrap
past midnight are extended by 24h so the arithmetic stays linear; the segment is
counted on the day it *starts* (per the locked rule).

ALL_DAY ("זמין") convention
---------------------------
"זמין" means the guard is available for **every shift that day**. For hour
counting we expand it to the union of the three configured *default* shift
windows (morning/evening/night). With the system defaults
(07:00–16:30, 15:00–23:00, 23:00–07:00) that union spans 07:00→07:00 next day,
i.e. a full 24h. The defaults are injectable (``all_day_windows``) so callers
can pass the admin-edited shift hours from settings; the constant below mirrors
``settings_service.SETTINGS_DEFAULTS`` as a DB-free fallback.
"""

from __future__ import annotations

from datetime import time

from app.constants import ShiftType

from .parser import Cell, CellKind

# (start, end) minutes from midnight; end is exclusive. end <= start ⇒ wraps.
Segment = tuple[int, int]

_DAY_MINUTES = 24 * 60

# DB-free mirror of settings_service.SETTINGS_DEFAULTS shift hours.
DEFAULT_SHIFT_WINDOWS: dict[ShiftType, tuple[time, time]] = {
    ShiftType.MORNING: (time(7, 0), time(16, 30)),
    ShiftType.AFTERNOON: (time(15, 0), time(23, 0)),
    ShiftType.NIGHT: (time(23, 0), time(7, 0)),
}


def _to_min(t: time) -> int:
    return t.hour * 60 + t.minute


def _window_segment(start: time, end: time) -> Segment:
    """A single window → a linear segment; wrap past midnight by +24h."""
    s = _to_min(start)
    e = _to_min(end)
    if e <= s:  # night window crossing midnight
        e += _DAY_MINUTES
    return (s, e)


def merge_segments(segments: list[Segment]) -> list[Segment]:
    """Merge overlapping **or touching** segments into a minimal list."""
    if not segments:
        return []
    ordered = sorted(segments)
    merged: list[Segment] = [ordered[0]]
    for s, e in ordered[1:]:
        ls, le = merged[-1]
        if s <= le:  # overlap OR touch (s == le) → extend
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def merge_day(
    cells: dict[ShiftType, Cell],
    all_day_windows: dict[ShiftType, tuple[time, time]] | None = None,
) -> list[Segment]:
    """Reduce one day's shift cells to a minimal union of segments.

    ``WINDOW`` → its time range; ``ALL_DAY`` → the union of all default shift
    windows; ``UNAVAILABLE`` → ignored.
    """
    windows = all_day_windows or DEFAULT_SHIFT_WINDOWS
    raw: list[Segment] = []
    for cell in cells.values():
        if cell.kind == CellKind.WINDOW and cell.start and cell.end:
            raw.append(_window_segment(cell.start, cell.end))
        elif cell.kind == CellKind.ALL_DAY:
            for start, end in windows.values():
                raw.append(_window_segment(start, end))
        # UNAVAILABLE → contributes nothing
    return merge_segments(raw)


def day_hours(segments: list[Segment]) -> float:
    """Total hours covered by merged segments (assumed already merged)."""
    total_min = sum(e - s for s, e in segments)
    return round(total_min / 60, 2)


def weekly_hours(
    guard_cells: dict[int, dict[ShiftType, Cell]],
    all_day_windows: dict[ShiftType, tuple[time, time]] | None = None,
) -> float:
    """Sum of union-based day hours across all days (night counted on its start day)."""
    total = 0.0
    for day_cells in guard_cells.values():
        total += day_hours(merge_day(day_cells, all_day_windows))
    return round(total, 2)


def format_segment(segment: Segment) -> str:
    """Render a segment as ``HH:MM–HH:MM`` (en-dash), wrapping minutes mod 24h."""
    s, e = segment
    sh, sm = divmod(s % _DAY_MINUTES, 60)
    eh, em = divmod(e % _DAY_MINUTES, 60)
    return f"{sh:02d}:{sm:02d}–{eh:02d}:{em:02d}"


def format_day(segments: list[Segment]) -> list[str]:
    """Human-readable merged windows for a day (for the preview table)."""
    return [format_segment(seg) for seg in segments]
