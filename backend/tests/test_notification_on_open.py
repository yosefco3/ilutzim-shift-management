"""Tests for week-opened Telegram notification (P06)."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.notifications import notify_week_opened


# ---------------------------------------------------------------------------
# Helper to build a mock user object
# ---------------------------------------------------------------------------
def _make_user(telegram_id=None):
    u = MagicMock()
    u.telegram_id = telegram_id
    return u


# ===========================================================================
# Test: notify_week_opened sends to all guards with telegram_id
# ===========================================================================
@pytest.mark.asyncio
async def test_notify_week_opened_sends_to_all_guards():
    """Should call send_message for every user with a telegram_id."""
    ids = [111, 222, 333]
    with patch("app.bot.notifications.get_bot") as mock_bot_fn:
        mock_bot = AsyncMock()
        mock_bot_fn.return_value = mock_bot

        count = await notify_week_opened(date(2026, 6, 8), date(2026, 6, 14), ids)

    assert count == 3
    assert mock_bot.send_message.call_count == 3


# ===========================================================================
# Test: skips users without telegram_id (empty list)
# ===========================================================================
@pytest.mark.asyncio
async def test_notify_week_opened_handles_empty_list():
    """Should return 0 when no telegram_ids provided."""
    with patch("app.bot.notifications.get_bot") as mock_bot_fn:
        mock_bot = AsyncMock()
        mock_bot_fn.return_value = mock_bot

        count = await notify_week_opened(date(2026, 6, 8), date(2026, 6, 14), [])

    assert count == 0
    assert mock_bot.send_message.call_count == 0


# ===========================================================================
# Test: one failure doesn't stop others
# ===========================================================================
@pytest.mark.asyncio
async def test_notify_week_opened_continues_on_error():
    """If sending to one user fails, others should still be notified."""
    ids = [111, 222, 333]

    with patch("app.bot.notifications.get_bot") as mock_bot_fn:
        mock_bot = AsyncMock()
        mock_bot_fn.return_value = mock_bot

        # Second call raises
        mock_bot.send_message.side_effect = [
            None,                       # success (returns coro result None)
            Exception("boom"),          # failure
            None,                       # success
        ]

        count = await notify_week_opened(date(2026, 6, 8), date(2026, 6, 14), ids)

    # Two succeeded, one failed
    assert count == 2
    assert mock_bot.send_message.call_count == 3


# ===========================================================================
# Test: notification message format (DD/MM/YYYY + webapp URL)
# ===========================================================================
@pytest.mark.asyncio
async def test_notification_message_format():
    """Message must use DD/MM/YYYY format and expose a WebApp submit button."""
    captured: list[dict] = []

    with patch("app.bot.notifications.get_bot") as mock_bot_fn, \
         patch("app.config.settings") as mock_settings:
        mock_bot = AsyncMock()
        mock_bot_fn.return_value = mock_bot
        mock_settings.APP_URL = "https://example.com/app"

        # Make send_message capture the text and keyboard
        async def fake_send(**kwargs):
            captured.append(kwargs)

        mock_bot.send_message = AsyncMock(side_effect=fake_send)

        await notify_week_opened(date(2026, 6, 8), date(2026, 6, 14), [111])

    assert len(captured) == 1
    msg = captured[0]["text"]
    assert "08/06/2026" in msg
    assert "14/06/2026" in msg
    assert "שבוע חדש נפתח להגשה" in msg
    # URL is now exposed through a WebApp button, not the message body
    assert "https://example.com/app" not in msg

    # Since submit_reply_keyboard: the broadcast carries the composed BOTTOM
    # keyboard (persistent reply keyboard), submit row first — not an inline kb.
    from app.bot.keyboards.reply_kb import BTN_SUBMIT_CONSTRAINTS

    kb = captured[0]["reply_markup"]
    button = kb.keyboard[0][0]
    assert button.text == BTN_SUBMIT_CONSTRAINTS
    # The WebApp URL carries a cache-busting version param so Telegram's WebView
    # never serves guards a stale build (see app.version / app.bot.webapp).
    assert button.web_app.url.startswith("https://example.com/app/submit?")
    assert "v=" in button.web_app.url


# ===========================================================================
# Test: notify_week_locked sends to all guards
# ===========================================================================
@pytest.mark.asyncio
async def test_notify_week_locked_sends_to_all_guards():
    """Should call send_message for every user with a telegram_id."""
    from app.bot.notifications import notify_week_locked

    ids = [111, 222]
    with patch("app.bot.notifications.get_bot") as mock_bot_fn:
        mock_bot = AsyncMock()
        mock_bot_fn.return_value = mock_bot

        count = await notify_week_locked(date(2026, 6, 8), date(2026, 6, 14), ids)

    assert count == 2
    assert mock_bot.send_message.call_count == 2
    # Verify message format
    call_args = mock_bot.send_message.call_args_list[0]
    assert "08/06/2026" in call_args.kwargs["text"]
    assert "14/06/2026" in call_args.kwargs["text"]
    assert "נסגר" in call_args.kwargs["text"]


# ===========================================================================
# Test: notify_week_locked (the manual finalize/publish broadcast) → all guards
# ===========================================================================
@pytest.mark.asyncio
async def test_notify_week_locked_sends_to_all_guards():
    """Should call send_message for every user with a telegram_id."""
    from app.bot.notifications import notify_week_locked

    ids = [111, 222, 333]
    with patch("app.bot.notifications.get_bot") as mock_bot_fn:
        mock_bot = AsyncMock()
        mock_bot_fn.return_value = mock_bot

        count = await notify_week_locked(date(2026, 6, 8), date(2026, 6, 14), ids)

    assert count == 3
    assert mock_bot.send_message.call_count == 3
    # Verify message format
    call_args = mock_bot.send_message.call_args_list[0]
    assert "08/06/2026" in call_args.kwargs["text"]
    assert "ננעל" in call_args.kwargs["text"]
