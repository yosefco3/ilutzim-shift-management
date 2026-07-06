"""Unit tests for union-merge hour counting (step 02).

The critical rule: overlapping windows are merged and hours measured from the
union — 12h, not 13.5h.
"""

from datetime import time

from app.constants import ShiftType
from app.services.constraints_import.hours import (
    day_hours,
    format_day,
    merge_day,
    merge_segments,
    weekly_hours,
)
from app.services.constraints_import.parser import Cell, CellKind


def _win(start, end):
    s = time(*start)
    e = time(*end)
    return Cell(CellKind.WINDOW, start=s, end=e, wraps_midnight=e <= s)


def test_overlap_union_is_12_not_13_5():
    cells = {
        ShiftType.MORNING: _win((7, 0), (16, 30)),
        ShiftType.AFTERNOON: _win((15, 0), (19, 0)),
    }
    segs = merge_day(cells)
    assert len(segs) == 1
    assert day_hours(segs) == 12.0
    assert format_day(segs) == ["07:00–19:00"]


def test_touching_windows_merge():
    cells = {
        ShiftType.MORNING: _win((7, 0), (15, 0)),
        ShiftType.AFTERNOON: _win((15, 0), (23, 0)),
    }
    segs = merge_day(cells)
    assert len(segs) == 1
    assert day_hours(segs) == 16.0
    assert format_day(segs) == ["07:00–23:00"]


def test_night_wraps_midnight_eight_hours():
    cells = {ShiftType.NIGHT: _win((23, 0), (7, 0))}
    segs = merge_day(cells)
    assert day_hours(segs) == 8.0
    assert format_day(segs) == ["23:00–07:00"]


def test_disjoint_windows_stay_separate():
    cells = {
        ShiftType.MORNING: _win((7, 0), (11, 0)),
        ShiftType.AFTERNOON: _win((14, 0), (18, 0)),
    }
    segs = merge_day(cells)
    assert len(segs) == 2
    assert day_hours(segs) == 8.0


def test_unavailable_contributes_nothing():
    cells = {
        ShiftType.MORNING: Cell(CellKind.UNAVAILABLE),
        ShiftType.AFTERNOON: _win((15, 0), (19, 0)),
    }
    segs = merge_day(cells)
    assert day_hours(segs) == 4.0


def test_all_day_uses_default_shift_union():
    # "זמין" → union of default shift windows = full 24h with system defaults.
    cells = {ShiftType.MORNING: Cell(CellKind.ALL_DAY)}
    assert day_hours(merge_day(cells)) == 24.0


def test_merge_segments_primitive():
    assert merge_segments([(0, 10), (5, 20), (25, 30)]) == [(0, 20), (25, 30)]
    assert merge_segments([]) == []


def test_weekly_hours_sums_days():
    guard_cells = {
        0: {ShiftType.MORNING: _win((7, 0), (16, 30)),
            ShiftType.AFTERNOON: _win((15, 0), (19, 0))},  # 12h
        1: {ShiftType.NIGHT: _win((23, 0), (7, 0))},        # 8h
    }
    assert weekly_hours(guard_cells) == 20.0
