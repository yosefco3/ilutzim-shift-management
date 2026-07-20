"""Structural tests for the backend-agnostic schedule-grid model.

``build_schedule_grid`` is the single source of layout truth consumed by both the
Excel writer and the PNG renderer, so these assert the *shape* it produces —
titles, fills, split blocks, blocked ✕ cells, and fixed-count "חסר" holes —
independently of any rendering backend.
"""

import uuid
from datetime import date, timedelta

from app.schedule_builder.services.schedule_export_service import (
    Placement,
    PositionDay,
    PositionRow,
    WeekSchedule,
)
from app.services.schedule_grid_model import (
    PALETTE,
    build_schedule_grid,
)


def _week():
    start = date(2025, 1, 5)  # Sunday
    week = type("W", (), {})()
    week.id = uuid.uuid4()
    week.start_date = start
    week.end_date = start + timedelta(days=6)
    return week


def _pos_row(name, band, placements_by_day, active_days=None, canonical=None,
             gaps_by_day=None, is_event=False, event_required_count=None):
    active = active_days if active_days is not None else set(placements_by_day)
    gaps_by_day = gaps_by_day or {}
    days = []
    for d in range(7):
        placed = [
            Placement(user_id=uuid.uuid4(), user_name=n, start=s, end=e)
            for (n, s, e) in placements_by_day.get(d, [])
        ]
        days.append(PositionDay(
            day_index=d, date="", active=(d in active or bool(placed)),
            placements=placed, gaps=list(gaps_by_day.get(d, [])),
        ))
    canon = {"start": canonical[0], "end": canonical[1]} if canonical else None
    return PositionRow(
        position_id=uuid.uuid4(), name=name, band=band, days=days,
        canonical_window=canon, is_event=is_event,
        event_required_count=event_required_count,
    )


def _grid(rows):
    week = _week()
    schedule = WeekSchedule(
        week=week, days=[{"index": i, "date": ""} for i in range(7)],
        by_position=rows, by_guard=[],
    )
    return build_schedule_grid(schedule, week)


def test_title_and_header():
    grid = _grid([_pos_row("עמדה א", "morning", {0: [("דוד", "08:00", "16:00")]},
                           canonical=("08:00", "16:00"))]
                 )
    assert grid.title == "סידור עבודה — 2025-01-05 עד 2025-01-11"
    assert grid.header == ["עמדה", "ראשון", "שני", "שלישי", "רביעי",
                           "חמישי", "שישי", "שבת"]
    # No profile labels → all 7 day-label slots blank.
    assert grid.day_labels == [""] * 7


def test_day_labels_projected_onto_canonical_day_slots():
    week = _week()
    rows = [_pos_row("עמדה א", "morning", {0: [("דוד", "08:00", "16:00")]},
                     canonical=("08:00", "16:00"))]
    schedule = WeekSchedule(
        week=week, days=[{"index": i, "date": ""} for i in range(7)],
        by_position=rows, by_guard=[],
        # String day-index keyed, sparse (Monday=1, Wednesday=3).
        day_labels={"1": "חג", "3": "ט׳ באב"},
    )
    grid = build_schedule_grid(schedule, week)
    # Header names are untouched; labels land in the parallel day_labels list.
    assert grid.header[2] == "שני" and grid.header[4] == "רביעי"
    assert grid.day_labels == ["", "חג", "", "ט׳ באב", "", "", ""]


def test_regular_shift_shows_name_only_and_band_fill():
    grid = _grid([_pos_row("עמדה א", "morning",
                           {0: [("דוד", "08:00", "16:00")]},
                           active_days={0}, canonical=("08:00", "16:00"))])
    block = grid.blocks[0]
    assert block.span == 1
    # Name cell carries the position name + hours, tinted by its band.
    assert block.name.text == "עמדה א\n08:00–16:00"
    assert block.name.fill == PALETTE["band_morning"]
    # Sunday: a full-window shift shows just the name (no hours).
    sunday = block.days[0]
    assert sunday.cells[0].text == "דוד"
    assert sunday.cells[0].fill is None


def test_blocked_day_is_grey_cross():
    # Position active only Sunday; Monday is blocked → grey ✕.
    grid = _grid([_pos_row("עמדה א", "morning",
                           {0: [("דוד", "08:00", "16:00")]},
                           active_days={0}, canonical=("08:00", "16:00"))])
    monday = grid.blocks[0].days[1]
    assert monday.cells[0].text == "✕"
    assert monday.cells[0].fill == PALETTE["grey"]


def test_split_cell_spans_two_and_shows_hours():
    grid = _grid([_pos_row("עמדה ב", "evening",
                           {0: [("דוד", "16:00", "20:00"),
                                ("רון", "20:00", "24:00")]},
                           active_days={0}, canonical=("16:00", "24:00"))])
    block = grid.blocks[0]
    assert block.span == 2
    sunday = block.days[0]
    assert sunday.merged is False
    # Both guards show hours because the cell is split.
    texts = {c.text for c in sunday.cells}
    assert "דוד\n16:00–20:00" in texts
    assert "רון\n20:00–24:00" in texts


def test_fixed_count_event_shows_missing_slot():
    grid = _grid([_pos_row("רענון", "morning",
                           {0: [("דוד", "09:00", "12:00")]},
                           active_days={0}, canonical=("09:00", "12:00"),
                           is_event=True, event_required_count=2)])
    block = grid.blocks[0]
    assert block.span == 2  # tiled into the two required slots
    assert block.name.fill == PALETTE["event_name"]
    sunday = block.days[0]
    assert sunday.merged is False
    texts = [c.text for c in sunday.cells]
    assert "דוד" in texts
    assert "חסר" in texts  # the missing participant
    missing = next(c for c in sunday.cells if c.text == "חסר")
    assert missing.fill == PALETTE["empty"]


def test_not_happening_event_is_omitted():
    grid = _grid([_pos_row("רענון", "morning", {}, active_days=set(),
                           is_event=True, event_required_count=2)])
    assert grid.blocks == []


def test_gap_cell_shows_hours_in_amber():
    grid = _grid([_pos_row("עמדה ג", "night",
                           {0: [("דוד", "00:00", "04:00")]},
                           active_days={0}, canonical=("00:00", "08:00"),
                           gaps_by_day={0: [("04:00", "08:00")]})])
    block = grid.blocks[0]
    assert block.span == 2
    gap = next(c for c in block.days[0].cells if c.text == "04:00–08:00")
    assert gap.fill == PALETTE["empty"]
