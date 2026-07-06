"""Unit tests for the pure constraints-xlsx parser (step 01).

Tested against the real sample workbook copied into ``tests/fixtures`` so the
test is independent of the repo-root path.
"""

from datetime import date, time
from pathlib import Path

import pytest

from app.constants import ShiftType
from app.services.constraints_import import (
    CellKind,
    parse_constraints_xlsx,
)

FIXTURE = Path(__file__).parent / "fixtures" / "דוגמה_אילוצים_מאבטחים.xlsx"


@pytest.fixture(scope="module")
def parsed():
    return parse_constraints_xlsx(FIXTURE.read_bytes())


def _guard(parsed, name):
    return next(g for g in parsed.guards if g.name == name)


def test_five_guards_in_order(parsed):
    assert [g.name for g in parsed.guards] == [
        "אבי כהן",
        "בני לוי",
        "גדי מזרחי",
        "דנה אזולאי",
        "הראל ביטון",
    ]


def test_week_range(parsed):
    assert parsed.week_start == date(2026, 6, 14)
    assert parsed.week_end == date(2026, 6, 20)


def test_no_errors_on_valid_file(parsed):
    assert parsed.errors == []


def test_avi_cohen_cells(parsed):
    g = _guard(parsed, "אבי כהן")
    assert g.notes == "מעדיף משמרות בוקר"

    # ראשון (day 0) / MORNING = 07:00–16:00 window
    sun = g.cells[0][ShiftType.MORNING]
    assert sun.kind == CellKind.WINDOW
    assert sun.start == time(7, 0) and sun.end == time(16, 0)
    assert sun.wraps_midnight is False

    # שלישי (day 2): MORNING 07:00–13:00, AFTERNOON 15:00–19:00
    tue_m = g.cells[2][ShiftType.MORNING]
    assert tue_m.kind == CellKind.WINDOW
    assert tue_m.start == time(7, 0) and tue_m.end == time(13, 0)
    tue_a = g.cells[2][ShiftType.AFTERNOON]
    assert tue_a.kind == CellKind.WINDOW
    assert tue_a.start == time(15, 0) and tue_a.end == time(19, 0)

    # שישי (day 5) / MORNING = "לא זמין" → UNAVAILABLE
    assert g.cells[5][ShiftType.MORNING].kind == CellKind.UNAVAILABLE


def test_beni_levi_night_wraps_midnight(parsed):
    g = _guard(parsed, "בני לוי")
    night = g.cells[0][ShiftType.NIGHT]
    assert night.kind == CellKind.WINDOW
    assert night.start == time(23, 0) and night.end == time(7, 0)
    assert night.wraps_midnight is True

    # שלישי (day 2) / MORNING = "לא זמין"
    assert g.cells[2][ShiftType.MORNING].kind == CellKind.UNAVAILABLE


def test_gadi_mizrahi(parsed):
    g = _guard(parsed, "גדי מזרחי")
    assert g.notes == "מילואים בתחילת השבוע"
    # ראשון (day 0) / MORNING = "לא זמין"
    assert g.cells[0][ShiftType.MORNING].kind == CellKind.UNAVAILABLE


def test_dana_azoulay_all_day(parsed):
    g = _guard(parsed, "דנה אזולאי")
    assert g.notes == "זמינה בכל המשמרות"
    # שבת (day 6) / MORNING = "זמין" → ALL_DAY
    sat = g.cells[6][ShiftType.MORNING]
    assert sat.kind == CellKind.ALL_DAY


def test_empty_cell_is_unavailable(parsed):
    # בני לוי ראשון/MORNING is an empty cell → UNAVAILABLE
    g = _guard(parsed, "בני לוי")
    assert g.cells[0][ShiftType.MORNING].kind == CellKind.UNAVAILABLE
