"""Golden-fixture parity — the Python side.

Each fixture in ``tests/fixtures/warnings/*.json`` holds an ``input`` (board /
assignments_by_cell / pool / policy) and the full ``expected`` output. The SAME
files are consumed by the JS Vitest parity test, so a threshold or rule changed
in one language and not the other turns one of these red. Single source of truth
for the fixtures: this directory (JS reads them by relative path).
"""

import json
from pathlib import Path

import pytest

from app.schedule_builder.services.warnings_service import compute_board_warnings

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "warnings"
FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_warnings_parity_fixture(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    inp = data["input"]
    result = compute_board_warnings(
        inp["board"], inp["assignments_by_cell"], inp["pool"], inp["policy"]
    )
    assert result == data["expected"]


def test_fixtures_exist():
    """Guard against an empty fixture dir silently passing the parametrize above."""
    assert len(FIXTURES) >= 8
