"""
Stage 3 / 01 step 3 — one-time GPS consent flow.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.bot.handlers.attendance import (
    CONSENT_CALLBACK,
    GPS_CONSENT_TEXT,
    consent_kb,
    on_consent_confirmed,
    send_consent_request,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository


async def _make_guard(db_session, telegram_id="111222333") -> User:
    user = User(
        phone_number="0501234567",
        first_name="יוסי",
        last_name="כהן",
        roles=[],
        telegram_id=telegram_id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _callback(telegram_id: int):
    """A minimal aiogram CallbackQuery stand-in."""
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
        data=CONSENT_CALLBACK,
    )


def test_consent_keyboard_and_text():
    kb = consent_kb()
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].callback_data == CONSENT_CALLBACK
    # The approved wording essentials are present.
    assert "ברגע ההחתמה בלבד" in GPS_CONSENT_TEXT
    assert "אין שום מעקב מיקום" in GPS_CONSENT_TEXT


@pytest.mark.asyncio
async def test_send_consent_request_sends_text_with_keyboard():
    message = SimpleNamespace(answer=AsyncMock())
    await send_consent_request(message)
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert args[0] == GPS_CONSENT_TEXT
    assert kwargs["reply_markup"] is not None


def _fake_session_factory(db_session):
    """Session shim: handler may commit/close without killing the test session."""

    async def fake():
        shim = SimpleNamespace(commit=db_session.commit, close=AsyncMock())
        return UserRepository(db_session), shim

    return fake


@pytest.mark.asyncio
async def test_confirm_records_timestamp_once(db_session):
    guard = await _make_guard(db_session)
    assert guard.gps_consent_at is None

    fake_session = _fake_session_factory(db_session)
    callback = _callback(111222333)
    with patch("app.bot.handlers.attendance._get_user_session", side_effect=fake_session):
        await on_consent_confirmed(callback)

    await db_session.refresh(guard)
    first_stamp = guard.gps_consent_at
    assert first_stamp is not None
    callback.message.answer.assert_awaited()  # thanks message

    # Tapping again keeps the ORIGINAL timestamp (one-time consent).
    callback2 = _callback(111222333)
    with patch("app.bot.handlers.attendance._get_user_session", side_effect=fake_session):
        await on_consent_confirmed(callback2)
    await db_session.refresh(guard)
    assert guard.gps_consent_at == first_stamp


@pytest.mark.asyncio
async def test_confirm_unknown_user_gets_start_hint(db_session):
    fake_session = _fake_session_factory(db_session)
    callback = _callback(999999999)
    with patch("app.bot.handlers.attendance._get_user_session", side_effect=fake_session):
        await on_consent_confirmed(callback)

    args, _ = callback.message.answer.await_args
    assert "/start" in args[0]


def test_user_response_exposes_gps_consent():
    """The admin API schema carries the read-only consent field."""
    from app.schemas.user_schemas import UserResponse

    assert "gps_consent_at" in UserResponse.model_fields
