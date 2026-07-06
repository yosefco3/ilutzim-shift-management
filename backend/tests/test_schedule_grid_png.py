"""Tests for the Pillow PNG renderer of the schedule grid.

Pure — builds a small ``ScheduleGrid`` by hand (staffed cell, split cell with
hours, a blocked ✕ day, a fixed-count "חסר" hole) and renders it, asserting the
bytes are a real PNG of a phone-legible width. No DB / async.
"""

import io

import pytest

from app.services.schedule_grid_model import (
    PALETTE,
    Block,
    Cell,
    DayColumn,
    ScheduleGrid,
)

pytest.importorskip("PIL")
pytest.importorskip("bidi")

from app.services.schedule_grid_png import (  # noqa: E402
    _FONT_BOLD,
    _FONT_REGULAR,
    render_schedule_grid_png,
)


def _sample_grid() -> ScheduleGrid:
    header = ["עמדה", "ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]

    # Block 1: a regular position — Sunday staffed (name only), Monday blocked ✕,
    # rest empty amber. span 1.
    days1 = [DayColumn(merged=False, cells=[Cell(text="דוד", fill=None)])]
    days1.append(DayColumn(merged=False, cells=[Cell(text="✕", fill=PALETTE["grey"])]))
    for _ in range(5):
        days1.append(DayColumn(merged=False, cells=[Cell(text=None, fill=PALETTE["empty"])]))
    block1 = Block(
        name=Cell(text="עמדה ראשית\n08:00–16:00", fill=PALETTE["band_morning"], wrap=True),
        span=1, days=days1,
    )

    # Block 2: a split cell (two guards with hours) + a fixed-count "חסר". span 2.
    split = DayColumn(merged=False, cells=[
        Cell(text="רון\n16:00–20:00", fill=None, wrap=True),
        Cell(text="חסר", fill=PALETTE["empty"]),
    ])
    days2 = [split] + [
        DayColumn(merged=True, cells=[Cell(text=None, fill=PALETTE["event"])])
        for _ in range(6)
    ]
    block2 = Block(
        name=Cell(text="רענון\n16:00–20:00", fill=PALETTE["event_name"], wrap=True),
        span=2, days=days2,
    )

    return ScheduleGrid(
        title="סידור עבודה — 2025-01-05 עד 2025-01-11",
        header=header, blocks=[block1, block2],
    )


def test_fonts_are_bundled_and_loadable():
    from PIL import ImageFont
    assert _FONT_REGULAR.exists() and _FONT_BOLD.exists()
    ImageFont.truetype(str(_FONT_REGULAR), 16)
    ImageFont.truetype(str(_FONT_BOLD), 16)


def test_renders_a_valid_png():
    data = render_schedule_grid_png(_sample_grid())
    assert isinstance(data, bytes) and len(data) > 100
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_is_phone_legible_width():
    from PIL import Image
    img = Image.open(io.BytesIO(render_schedule_grid_png(_sample_grid())))
    assert img.format == "PNG"
    # Width bounded so Telegram's photo compression keeps text legible.
    assert img.width <= 1280
    # Height grows with the blocks (span 1 + span 2 = 3 sub-rows) → non-trivial.
    assert img.height > 100


def test_font_uses_basic_layout_engine():
    """Regression guard: fonts MUST use the BASIC layout engine. The default
    engine uses libraqm (when present) which re-applies the bidi algorithm on top
    of our python-bidi ``get_display`` — double-reordering Hebrew back to broken
    RTL (e.g. "עמדה" → "הדמע"). Whether raqm is compiled in varies by build, so
    pinning BASIC is what keeps the render correct and identical everywhere."""
    from PIL import ImageFont
    from app.services.schedule_grid_png import _font
    assert _font(20).layout_engine == ImageFont.Layout.BASIC
    assert _font(20, bold=True).layout_engine == ImageFont.Layout.BASIC


def test_bidi_reorders_hebrew_to_visual_order():
    """Sanity that python-bidi is doing the single RTL pass we rely on: it must
    reverse a Hebrew word to visual order. Combined with the BASIC layout engine
    (no second raqm pass), that is the correctness contract for the render."""
    from bidi.algorithm import get_display
    assert get_display("עמדה") == "הדמע"


def test_empty_grid_still_renders():
    grid = ScheduleGrid(title="ריק", header=["עמדה"] + ["yom"] * 7, blocks=[])
    data = render_schedule_grid_png(grid)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
