"""Pillow renderer: a :class:`ScheduleGrid` → PNG bytes.

The guard-facing schedule is delivered on publish as a **photo** (see
``send_personal_schedules``) rather than an ``.xlsx`` — an image opens with one tap
on a phone. This paints the exact same shared grid model the Excel uses
(``schedule_grid_model``), so colours and layout match.

Hebrew is right-to-left: Pillow draws left-to-right, so each line is reordered with
``python-bidi`` before drawing and columns are laid out right-to-left (the ``עמדה``
column on the far right, ``ראשון…שבת`` leftward) to mirror the Excel's RTL sheet.

A bundled DejaVu Sans (in ``app/assets/fonts``) is used so the image renders the
same in the container as locally — no system-font dependency — and it carries the
Hebrew, ``✕`` and dash glyphs the grid needs.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from app.services.schedule_grid_model import PALETTE

try:
    from bidi.algorithm import get_display
    from PIL import Image, ImageDraw, ImageFont

    HAS_PILLOW = True
except ImportError:  # pragma: no cover - exercised only where Pillow is absent
    HAS_PILLOW = False


_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_REGULAR = _FONT_DIR / "DejaVuSans.ttf"
_FONT_BOLD = _FONT_DIR / "DejaVuSans-Bold.ttf"

# ── Layout metrics (px). Total width = NAME_W + 7·DAY_W ≤ 1280 so Telegram's
# photo compression keeps the text legible on a phone. ──────────────────
_NAME_W = 200
_DAY_W = 150
_TITLE_H = 52
_HEADER_H = 42
_ROW_H = 46            # one sub-row; fits a 2-line name+hours cell
_PAD = 12              # outer margin
_FS_TITLE = 24
_FS_HEADER = 18
_FS_CELL = 17
_LINE_H = 20

_BORDER = (150, 150, 150)      # thin cell grid
_SEP = (60, 60, 60)            # heavy line under each position block
_INK = (26, 26, 26)            # cell text
_WHITE = (255, 255, 255)


def _rgb(hex_color: str | None) -> tuple[int, int, int]:
    if not hex_color:
        return _WHITE
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _font(size: int, bold: bool = False):
    # Force the BASIC layout engine so we control RTL ourselves via python-bidi
    # (``get_display``). The default engine uses libraqm *when Pillow was built
    # with it*, which re-applies the bidi algorithm — double-reordering our
    # already-visual strings back to broken RTL (e.g. "עמדה" → "הדמע"). Whether
    # raqm is present varies by build, so pinning BASIC keeps the render correct
    # and identical in every environment.
    return ImageFont.truetype(
        str(_FONT_BOLD if bold else _FONT_REGULAR),
        size,
        layout_engine=ImageFont.Layout.BASIC,
    )


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Greedy word-wrap a single logical line to ``max_w`` px."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def _draw_text(draw, box, text: str, font, color, max_w: int) -> None:
    """Centre ``text`` (possibly multi-line via ``\\n``) inside ``box`` = (x0,y0,x1,y1),
    reordering each line for RTL display."""
    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2
    logical_lines: list[str] = []
    for raw in text.split("\n"):
        logical_lines.extend(_wrap(draw, raw, font, max_w))
    total_h = len(logical_lines) * _LINE_H
    ly = (y0 + y1) / 2 - total_h / 2 + _LINE_H / 2
    for line in logical_lines:
        draw.text((cx, ly), get_display(line), font=font, fill=color, anchor="mm")
        ly += _LINE_H


def render_schedule_grid_png(grid: Any) -> bytes:
    """Render a :class:`ScheduleGrid` to PNG bytes (see module docstring)."""
    if not HAS_PILLOW:
        raise RuntimeError("Pillow + python-bidi are required for PNG export")

    n_days = 7
    total_w = _NAME_W + n_days * _DAY_W
    body_h = sum(b.span for b in grid.blocks) * _ROW_H

    # A scratch canvas just to measure wrapped label lines before sizing the real
    # image (Pillow needs a draw context for ``textlength``).
    _measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f_title, f_header, f_cell = (
        _font(_FS_TITLE, bold=True),
        _font(_FS_HEADER, bold=True),
        _font(_FS_CELL),
    )
    day_labels = list(getattr(grid, "day_labels", None) or [])
    # Header height grows to fit the day name (1 line) plus any wrapped label lines.
    label_lines_by_day = [
        _wrap(_measure, day_labels[d], f_header, _DAY_W - 8) if d < len(day_labels)
        and day_labels[d] else []
        for d in range(n_days)
    ]
    max_label_lines = max((len(ls) for ls in label_lines_by_day), default=0)
    header_h = _HEADER_H + max_label_lines * _LINE_H

    total_h = _PAD + _TITLE_H + header_h + body_h + _PAD
    width = total_w + 2 * _PAD

    img = Image.new("RGB", (width, total_h), _WHITE)
    draw = ImageDraw.Draw(img)

    left = _PAD
    right = left + total_w

    # Column x-ranges, laid out RIGHT-to-LEFT: name column on the far right,
    # day 0 (ראשון) just left of it, day 6 (שבת) on the far left.
    def name_x() -> tuple[int, int]:
        return right - _NAME_W, right

    def day_x(d: int) -> tuple[int, int]:
        x1 = right - _NAME_W - d * _DAY_W
        return x1 - _DAY_W, x1

    # Title band.
    y = _PAD
    _draw_text(draw, (left, y, right, y + _TITLE_H), grid.title, f_title,
               _INK, total_w - 2 * _PAD)
    y += _TITLE_H

    # Header row.
    def cell_rect(x0, y0, x1, y1, fill, text=None, font=None, color=_INK,
                  heavy_bottom=False):
        draw.rectangle([x0, y0, x1, y1], fill=fill)
        draw.rectangle([x0, y0, x1, y1], outline=_BORDER, width=1)
        if heavy_bottom:
            draw.line([(x0, y1), (x1, y1)], fill=_SEP, width=3)
        if text:
            _draw_text(draw, (x0, y0, x1, y1), text, font or f_cell, color,
                       (x1 - x0) - 8)

    nx0, nx1 = name_x()
    cell_rect(nx0, y, nx1, y + header_h, _rgb(PALETTE["header"]),
              grid.header[0], f_header, _WHITE)
    for d in range(n_days):
        dx0, dx1 = day_x(d)
        # A day column shows its name and, when the profile set one, its label on a
        # second line (e.g. "שני\nחג") so guards see the annotation on the image.
        label = day_labels[d] if d < len(day_labels) else ""
        text = f"{grid.header[d + 1]}\n{label}" if label else grid.header[d + 1]
        cell_rect(dx0, y, dx1, y + header_h, _rgb(PALETTE["header"]),
                  text, f_header, _WHITE)
    y += header_h

    # Position blocks.
    for block in grid.blocks:
        span = block.span
        block_h = span * _ROW_H
        # Name cell — merged down the whole block, on the far right.
        nx0, nx1 = name_x()
        cell_rect(nx0, y, nx1, y + block_h, _rgb(block.name.fill),
                  block.name.text, f_cell, _INK, heavy_bottom=True)
        # Day columns.
        for d in range(n_days):
            col = block.days[d]
            dx0, dx1 = day_x(d)
            if col.merged:
                c = col.cells[0]
                cell_rect(dx0, y, dx1, y + block_h, _rgb(c.fill), c.text,
                          f_cell, _INK, heavy_bottom=True)
            else:
                for p in range(span):
                    c = col.cells[p]
                    ry0 = y + p * _ROW_H
                    cell_rect(dx0, ry0, dx1, ry0 + _ROW_H, _rgb(c.fill),
                              c.text, f_cell, _INK,
                              heavy_bottom=(p == span - 1))
        y += block_h

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
