"""
Quiz guard-rails (2026-07-18 fixes): one open quiz at a time + quiz exit.

- ``start_attempt`` refuses a start while an attempt on a DIFFERENT procedure
  is IN_PROGRESS (the block message names the blocking procedure); a
  same-procedure restart keeps the existing supersede behavior.
- ``quit_attempt`` abandons the open attempt; late answers to its polls are
  ignored; the quit is idempotent.
- Every quiz poll carries the '🚪 יציאה מהמבחן' inline button.
"""

import pytest
from unittest.mock import MagicMock

from app.bot import quiz_sender
from app.exceptions import ValidationException
from app.procedures.constants import AttemptStatus
from app.procedures.dependencies import build_quiz_service
from app.procedures.repositories import QuizAttemptRepository

from tests.test_procedures_quiz_start import (
    _fake_bot,
    _guard,
    _published_with_questions,
)


@pytest.mark.asyncio
async def test_second_quiz_blocked_while_another_is_open(db_session):
    """A start on procedure B is refused while procedure A's quiz is open."""
    proc_a = await _published_with_questions(db_session)
    proc_b = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    svc = build_quiz_service(db_session)

    await svc.start_attempt(guard.id, proc_a.id)

    with pytest.raises(ValidationException) as exc_info:
        await svc.start_attempt(guard.id, proc_b.id)
    assert "מבחן פתוח" in exc_info.value.message
    assert proc_a.title in exc_info.value.message

    # Only procedure A's attempt exists, still IN_PROGRESS.
    open_attempt = await QuizAttemptRepository(db_session).get_any_in_progress(guard.id)
    assert open_attempt is not None and open_attempt.procedure_id == proc_a.id


@pytest.mark.asyncio
async def test_same_procedure_restart_still_supersedes(db_session):
    """The cross-procedure gate must NOT break the same-procedure retake."""
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    svc = build_quiz_service(db_session)

    first = await svc.start_attempt(guard.id, proc.id)
    second = await svc.start_attempt(guard.id, proc.id)
    assert second.created is True

    await db_session.refresh(first.attempt)
    assert first.attempt.status == AttemptStatus.ABANDONED


@pytest.mark.asyncio
async def test_quit_abandons_and_unblocks_other_quizzes(db_session):
    """Exit → the open attempt is ABANDONED and another quiz can start."""
    proc_a = await _published_with_questions(db_session)
    proc_b = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    svc = build_quiz_service(db_session)

    started = await svc.start_attempt(guard.id, proc_a.id)
    assert await svc.quit_attempt(guard.id) is True
    assert await svc.quit_attempt(guard.id) is False  # idempotent

    await db_session.refresh(started.attempt)
    assert started.attempt.status == AttemptStatus.ABANDONED

    # The gate is lifted — procedure B starts fine now.
    assert (await svc.start_attempt(guard.id, proc_b.id)).created is True


@pytest.mark.asyncio
async def test_late_answer_after_quit_is_ignored(db_session, monkeypatch):
    """An answer to a poll of a quit attempt is dropped (known=False)."""
    fake = _fake_bot()
    monkeypatch.setattr(quiz_sender, "get_bot", lambda: fake)
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    svc = build_quiz_service(db_session)

    start = await svc.start_attempt(guard.id, proc.id)
    assert await quiz_sender.send_current_question(111, start.attempt, svc)
    await db_session.commit()

    await svc.quit_attempt(guard.id)
    outcome = await svc.record_answer("poll-1", 0)
    assert outcome.known is False


@pytest.mark.asyncio
async def test_quiz_poll_carries_the_quit_button(db_session, monkeypatch):
    """Every quiz poll ships with the 🚪 exit inline button."""
    from app.bot.keyboards.procedures import QUIZ_QUIT_CB

    captured = {}
    bot = MagicMock()

    async def _send_poll(*args, **kwargs):
        captured.update(kwargs)
        msg = MagicMock()
        msg.poll = MagicMock(id="poll-x")
        return msg

    bot.send_poll = _send_poll
    monkeypatch.setattr(quiz_sender, "get_bot", lambda: bot)

    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    svc = build_quiz_service(db_session)
    start = await svc.start_attempt(guard.id, proc.id)
    assert await quiz_sender.send_current_question(111, start.attempt, svc)

    kb = captured["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == QUIZ_QUIT_CB
