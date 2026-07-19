"""
submit_reply_keyboard — the composed persistent bottom keyboard.

``compose_reply_kb`` unit-composition per (week_open, attendance_enabled), the
TEXT submit button (a keyboard-button web_app gets no initData — step 03),
the submit_button handler's inline answer, and ``main_reply_kb``'s never-raise
fallback (EDGE S2/S3 in features-prompts/submit_reply_keyboard/EDGE_CASES.md).
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


def test_compose_submit_button_is_plain_text():
    """Step 03: the submit button must be a TEXT button, never web_app —
    Telegram passes empty initData to keyboard-button Mini Apps, so a web_app
    button here cannot authenticate (prod 401 / dev wrong-user bypass)."""
    kb = compose_reply_kb(week_open=True, attendance_enabled=False)
    btn = kb.keyboard[0][0]
    assert btn.web_app is None
    assert btn.text == BTN_SUBMIT_CONSTRAINTS


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


# ── Step 02: the open/closed broadcasts carry the composed keyboard ─────────


@pytest.mark.asyncio
async def test_notify_week_closed_reverts_to_punch_only():
    """EDGE S3 counterpart: the auto-lock broadcast drops the submit row."""
    from datetime import date

    from app.bot.notifications import notify_week_closed

    captured = []
    with patch("app.bot.notifications.get_bot") as bot_fn, patch(
        "app.config.get_settings"
    ) as gs:
        gs.return_value.ATTENDANCE_ENABLED = True
        bot = bot_fn.return_value

        async def fake_send(**kwargs):
            captured.append(kwargs)

        bot.send_message = fake_send
        await notify_week_closed(date(2026, 7, 12), date(2026, 7, 18), [111])

    kb = captured[0]["reply_markup"]
    assert _texts(kb) == [[BTN_PUNCH_IN, BTN_PUNCH_OUT]]


# ── Step 03: the submit TEXT button is answered with an inline web_app button ─


class _FakeMessage:
    """Captures message.answer(text, reply_markup=...) calls."""

    def __init__(self):
        self.answers = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_submit_button_open_week_answers_with_inline_webapp(monkeypatch):
    """Open week → the answer carries the INLINE submit button (has initData)."""
    from app.bot.handlers.submit_button import on_submit_button

    class _FakeRepo:
        def __init__(self, session):
            pass

        async def get_current_open_week(self):
            return object()

    monkeypatch.setattr(
        "app.repositories.schedule_week_repository.ScheduleWeekRepository", _FakeRepo
    )
    msg = _FakeMessage()
    await on_submit_button(msg)

    _text, kb = msg.answers[0]
    btn = kb.inline_keyboard[0][0]
    assert btn.web_app is not None
    assert "/submit" in btn.web_app.url


@pytest.mark.asyncio
async def test_submit_button_no_open_week_refreshes_keyboard(monkeypatch):
    """Stale button after the silent rollover → 'no open week' + fresh keyboard
    (punch-only here) so the dead submit button goes away."""
    from app.bot.handlers.submit_button import on_submit_button

    class _FakeRepo:
        def __init__(self, session):
            pass

        async def get_current_open_week(self):
            return None

    monkeypatch.setattr(
        "app.repositories.schedule_week_repository.ScheduleWeekRepository", _FakeRepo
    )
    msg = _FakeMessage()
    with patch("app.config.get_settings") as gs:
        gs.return_value.ATTENDANCE_ENABLED = True
        await on_submit_button(msg)

    text, kb = msg.answers[0]
    assert "אין שבוע פתוח" in text
    assert _texts(kb) == [[BTN_PUNCH_IN, BTN_PUNCH_OUT]]


@pytest.mark.asyncio
async def test_notify_week_closed_removes_keyboard_when_attendance_off():
    """EDGE S3: no punch row to fall back to → ReplyKeyboardRemove."""
    from datetime import date

    from aiogram.types import ReplyKeyboardRemove

    from app.bot.notifications import notify_week_closed

    captured = []
    with patch("app.bot.notifications.get_bot") as bot_fn, patch(
        "app.config.get_settings"
    ) as gs:
        gs.return_value.ATTENDANCE_ENABLED = False
        bot = bot_fn.return_value

        async def fake_send(**kwargs):
            captured.append(kwargs)

        bot.send_message = fake_send
        await notify_week_closed(date(2026, 7, 12), date(2026, 7, 18), [111])

    assert isinstance(captured[0]["reply_markup"], ReplyKeyboardRemove)
