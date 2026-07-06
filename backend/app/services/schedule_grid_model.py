"""Backend-agnostic model of the *built* schedule grid.

``export_schedule_grid`` (Excel) and ``render_schedule_grid_png`` (Pillow) both
consume the ``ScheduleGrid`` produced by :func:`build_schedule_grid`, so the two
products can never drift: all layout decisions (which cell is amber, where a block
splits into sub-rows, when a shift shows its hours) live here **once**.

The model carries plain hex colours and text — no openpyxl / PIL types — so each
renderer only has to *paint* it. Mirrors the read-model cuts described in
``schedule_export_service`` (``by_position`` → one block per position, 7 days).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schedule_builder.utils import intervals as iv

# ── Palette — single source of truth for every fill (hex "RRGGBB") ──────
# The Excel builds its PatternFills from these, so a colour tweak here changes
# both the .xlsx and the PNG at once.
PALETTE: dict[str, str] = {
    "header": "4472C4",       # header row — white bold text on blue
    "empty": "FFC000",        # amber — uncovered active cell / gap / missing slot
    "event": "E4DFEC",        # event position cell (staffed or empty)
    "event_name": "CCC0DA",   # event position name block (deeper purple)
    "grey": "E7E6E6",         # blocked / inactive day, and short-day padding
    "band_morning": "FFF2CC",
    "band_evening": "FCE4D6",
    "band_night": "D9E1F2",
}

_BAND_FILL = {
    "morning": PALETTE["band_morning"],
    "evening": PALETTE["band_evening"],
    "night": PALETTE["band_night"],
}

# Hebrew weekday order (Sunday=0 … Saturday=6). Re-exported for renderers.
DAY_NAMES_HE = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]


@dataclass
class Cell:
    """One painted cell. ``fill=None`` means white; ``wrap`` picks centred-wrap
    (multi-line name+hours) over plain centred text."""

    text: str | None = None
    fill: str | None = None
    wrap: bool = False


@dataclass
class DayColumn:
    """A position block's cell(s) for one day. ``merged`` → a single cell spanning
    the whole block (``cells`` length 1); otherwise one ``Cell`` per sub-row
    (``cells`` length == block span)."""

    merged: bool
    cells: list[Cell]


@dataclass
class Block:
    """One position row-block: a merged name cell + 7 day columns, ``span`` tall."""

    name: Cell
    span: int
    days: list[DayColumn] = field(default_factory=list)


@dataclass
class ScheduleGrid:
    title: str
    header: list[str]
    blocks: list[Block]


def build_schedule_grid(schedule: Any, week: Any) -> ScheduleGrid:
    """Turn the ``by_position`` read-model cut into a renderer-neutral grid.

    Ports the layout logic that used to live inside ``export_schedule_grid``:
    per position, each day stacks its guards *and* its uncovered gaps as sub-rows;
    a cell only shows hours when the shift is *exceptional* (split, or deviating
    from the position's regular window); fixed-count events tile into their full
    slot count and paint the missing participants amber ("חסר").
    """
    title = f"סידור עבודה — {week.start_date} עד {week.end_date}"
    header = ["עמדה"] + DAY_NAMES_HE

    blocks: list[Block] = []
    for row in schedule.by_position:
        days_by_index = {d.day_index: d for d in row.days}
        canon = row.canonical_window or {}
        is_event = getattr(row, "is_event", False)
        # A fixed participant count (event only): the cell tiles into this many
        # participant slots and paints the missing ones amber. None = unlimited.
        event_slots = (
            getattr(row, "event_required_count", None) if is_event else None
        )
        # A non-splitting event with NO guards anywhere this week is omitted — an
        # event that isn't happening shouldn't clutter the sheet.
        if is_event and not any(d.placements for d in row.days):
            continue

        # An event cell is always purple (staffed or empty); a normal unstaffed
        # active cell stays amber.
        cell_fill = PALETTE["event"] if is_event else None
        empty_fill = PALETTE["event"] if is_event else PALETTE["empty"]

        # Each day stacks its guards AND uncovered gaps as sub-rows in
        # chronological order; the block is as tall as the busiest day.
        entries_by_day: dict[int, list] = {}
        for di in range(7):
            d = days_by_index.get(di)
            items: list = []
            if d is not None:
                items = (
                    [("guard", pl) for pl in d.placements]
                    + [("gap", g) for g in d.gaps]
                )
                items.sort(
                    key=lambda it: iv.to_min(
                        it[1].start if it[0] == "guard" else it[1][0]
                    )
                )
            entries_by_day[di] = items
        span = max([len(e) for e in entries_by_day.values()] + [1])
        # A fixed-count event always tiles into its full slot count so the missing
        # participants show as amber holes (backend caps guards ≤ N).
        if event_slots:
            span = max(span, event_slots)

        # Position name + its regular hours, tinted by its display band. The
        # canonical hours live under the name so a cell only needs hours when it
        # *deviates*.
        name_label = row.name
        if canon.get("start") and canon.get("end"):
            name_label = f"{row.name}\n{canon['start']}–{canon['end']}"
        name_cell = Cell(
            text=name_label,
            fill=PALETTE["event_name"] if is_event else _BAND_FILL.get(row.band),
            wrap=True,
        )

        day_cols: list[DayColumn] = []
        for day_index in range(7):
            day = days_by_index.get(day_index)
            entries = entries_by_day[day_index]

            # A day needing fewer sub-rows than the block is tall merges down into
            # one centred cell — so only genuinely-split cells render as two rows.
            # Exception: a *happening* fixed-count event day (≥1 guard) always
            # renders all N slots so the missing participants show.
            merge_lone = span > 1 and len(entries) <= 1
            if event_slots and len(entries) >= 1:
                merge_lone = False

            if merge_lone:
                if day is None or not day.active:
                    cell = Cell(text="✕", fill=PALETTE["grey"], wrap=False)
                elif not entries:
                    cell = Cell(text=None, fill=empty_fill, wrap=False)
                else:
                    placed = entries[0][1]
                    exceptional = (placed.start, placed.end) != (
                        canon.get("start"), canon.get("end")
                    )
                    cell = Cell(
                        text=(
                            f"{placed.user_name}\n{placed.start}–{placed.end}"
                            if exceptional else placed.user_name
                        ),
                        fill=cell_fill,
                        wrap=True,
                    )
                day_cols.append(DayColumn(merged=True, cells=[cell]))
                continue

            sub_cells: list[Cell] = []
            for p in range(span):
                if day is None or not day.active:
                    # Blocked day → grey; one ✕ mark on the top sub-row.
                    sub_cells.append(
                        Cell(
                            text="✕" if p == 0 else None,
                            fill=PALETTE["grey"], wrap=False,
                        )
                    )
                    continue
                if p >= len(entries):
                    if event_slots and entries:
                        # Missing participant in a happening fixed-count event.
                        sub_cells.append(
                            Cell(text="חסר", fill=PALETTE["empty"], wrap=False)
                        )
                        continue
                    # Wholly-unstaffed active cell → amber/event-purple; padding
                    # below a shorter day's content stays grey.
                    sub_cells.append(
                        Cell(
                            text=None,
                            fill=empty_fill if not entries else PALETTE["grey"],
                            wrap=False,
                        )
                    )
                    continue
                kind, data = entries[p]
                if kind == "gap":
                    gs, ge = data
                    sub_cells.append(
                        Cell(text=f"{gs}–{ge}", fill=PALETTE["empty"], wrap=True)
                    )
                    continue
                placed = data
                # Hours only when the shift is *exceptional*: the cell is split, or
                # the guard's hours deviate from the position's regular window.
                # Event guards all share the whole window, so a multi-guard event
                # cell isn't "split" — only a genuine deviation shows hours.
                exceptional = (placed.start, placed.end) != (
                    canon.get("start"), canon.get("end")
                )
                if not is_event:
                    exceptional = exceptional or len(entries) > 1
                sub_cells.append(
                    Cell(
                        text=(
                            f"{placed.user_name}\n{placed.start}–{placed.end}"
                            if exceptional else placed.user_name
                        ),
                        fill=PALETTE["event"] if is_event else None,
                        wrap=True,
                    )
                )
            day_cols.append(DayColumn(merged=False, cells=sub_cells))

        blocks.append(Block(name=name_cell, span=span, days=day_cols))

    return ScheduleGrid(title=title, header=header, blocks=blocks)
