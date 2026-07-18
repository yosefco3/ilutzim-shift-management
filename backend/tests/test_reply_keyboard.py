"""
submit_reply_keyboard — the composed persistent bottom keyboard.

``compose_reply_kb`` unit-composition per (week_open, attendance_enabled), the
web_app submit button target, and ``main_reply_kb``'s never-raise fallback
(EDGE S2/S3 in features-prompts/submit_reply_keyboard/EDGE_CASES.md).
"""

from unittest.mock import patch

import pytest

from app.bot.keyboards.attendance import BTN_PUNCH_IN, BTN_PUNCH_OUT
from app.bot.keyboards.reply_kb import (
    BTN_SUBMIT_CONSTRAINTS,
    compose_reply_kb,
    main_reply_kb,
)


def _texts(kb) -> list[list[str]]:
    return [[b.text for b in row] for row in kb.keyboard]


def test_compose_both_rows_submit_first():
    kb = compose_reply_kb(week_open=True, attendance_enabled=True)
    assert _texts(kb) == [
        [BTN_SUBMIT_CONSTRAINTS],
        [BTN_PUNCH_IN, BTN_PUNCH_OUT],
    ]
    assert kb.is_persistent is True


def test_compose_submit_button_opens_the_submit_webapp():
    kb = compose_reply_kb(week_open=True, attendance_enabled=False)
    btn = kb.keyboard[0][0]
    assert btn.web_app is not None
    assert "/submit" in btn.web_app.url
    assert "v=" in btn.web_app.url  # cache-busting, same as submit_webapp_url


def test_compose_closed_week_is_punch_only():
    kb = compose_reply_kb(week_open=False, attendance_enabled=True)
    assert _texts(kb) == [[BTN_PUNCH_IN, BTN_PUNCH_OUT]]
    assert kb.input_field_placeholder == "החתמת נוכחות"


def test_compose_no_rows_returns_none():
    assert compose_reply_kb(week_open=False, attendance_enabled=False) is None


@pytest.mark.asyncio
async def test_main_reply_kb_open_week_adds_submit_row(monkeypatch):
    """main_reply_kb reads the OPEN week through its own session seam."""

    class _FakeRepo:
        def __init__(self, session):
            pass

        async def get_current_open_week(self):
            return object()  # any truthy week

    monkeypatch.setattr(
        "app.repositories.schedule_week_repository.ScheduleWeekRepository", _FakeRepo
    )
    kb = await main_reply_kb()
    assert kb is not None
    assert _texts(kb)[0] == [BTN_SUBMIT_CONSTRAINTS]


@pytest.mark.asyncio
async def test_main_reply_kb_db_failure_degrades_to_punch_only(monkeypatch):
    """EDGE S2: a DB failure must never break a punch reply — punch-only kb."""

    class _Boom:
        def __init__(self, session):
            raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.repositories.schedule_week_repository.ScheduleWeekRepository", _Boom
    )
    with patch("app.config.get_settings") as gs:
        gs.return_value.ATTENDANCE_ENABLED = True
        kb = await main_reply_kb()
    assert kb is not None
    assert _texts(kb) == [[BTN_PUNCH_IN, BTN_PUNCH_OUT]]
