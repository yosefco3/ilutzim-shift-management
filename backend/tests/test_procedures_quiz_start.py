"""
Quiz start from the WebApp — the ``POST /procedures/{id}/quiz/start`` endpoint
and the shared ``start_and_send`` it funnels through (same path as the bot
callback). The endpoint function is invoked directly with a real in-memory
session so the DB state (attempt, poll link) is assertable; the bot send seam is
a fake (monkeypatched ``get_bot``), matching how the bot tests stub the aiogram
sends.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from unittest.mock import MagicMock

from app.bot import quiz_sender
from app.models.user import User
from app.procedures.constants import ProcedureStatus, QuestionSource
from app.procedures.controllers.procedure_controller import guard_start_quiz
from app.procedures.models import Procedure, QuizAttempt, QuizPollLink, QuizQuestion
from app.procedures.repositories import QuizAttemptRepository


async def _published_with_questions(db_session, n=7) -> Procedure:
    proc = Procedure(title="נהל", body_text="x", status=ProcedureStatus.PUBLISHED)
    db_session.add(proc)
    await db_session.flush()
    for i in range(n):
        db_session.add(
            QuizQuestion(
                procedure_id=proc.id, text=f"שאלה {i}",
                options=["א", "ב", "ג", "ד"], correct_index=i % 4,
                display_order=i, source=QuestionSource.AI,
            )
        )
    await db_session.commit()
    await db_session.refresh(proc)
    return proc


async def _guard(db_session, telegram_id="111") -> User:
    user = User(
        phone_number=f"050{telegram_id[-7:]}", first_name="ג", last_name="ב",
        roles=[], telegram_id=telegram_id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _fake_bot():
    """A fake bot whose send_poll yields a DISTINCT poll id per call (Telegram
    returns a unique id per poll; a constant would collide on the link PK across
    retries / re-sends in one session). Exposes ``send_poll_calls`` for asserts."""
    bot = MagicMock()
    state = {"n": 0}
    bot.send_poll_calls = 0

    async def _send_poll(*args, **kwargs):
        state["n"] += 1
        bot.send_poll_calls += 1
        msg = MagicMock()
        msg.poll = MagicMock(id=f"poll-{state['n']}")
        return msg

    bot.send_poll = _send_poll
    return bot


# ── start_and_send (shared path) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_and_send_creates_attempt_and_records_poll(db_session, monkeypatch):
    """The shared start path creates an attempt, sends the poll, records the link."""
    fake = _fake_bot()
    monkeypatch.setattr(quiz_sender, "get_bot", lambda: fake)
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)

    from app.procedures.dependencies import build_quiz_service

    quiz_service = build_quiz_service(db_session)
    outcome = await quiz_sender.start_and_send(guard.id, guard.id, proc.id, quiz_service)
    await db_session.commit()

    assert outcome.created is True
    assert outcome.sent is True
    assert fake.send_poll_calls == 1
    in_prog = await QuizAttemptRepository(db_session).get_in_progress(guard.id, proc.id)
    assert in_prog is not None
    # poll link recorded for the attempt
    links = (
        await db_session.execute(select(QuizPollLink).where(QuizPollLink.attempt_id == in_prog.id))
    ).scalars().all()
    assert len(links) == 1


@pytest.mark.asyncio
async def test_start_and_send_bot_none_returns_not_sent(db_session, monkeypatch):
    """Bot down → not sent, but the attempt is still created (caller persists it)."""
    monkeypatch.setattr(quiz_sender, "get_bot", lambda: None)
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    from app.procedures.dependencies import build_quiz_service

    quiz_service = build_quiz_service(db_session)
    outcome = await quiz_sender.start_and_send(guard.id, guard.id, proc.id, quiz_service)
    await db_session.commit()
    assert outcome.created is True
    assert outcome.sent is False
    # attempt exists, no poll link
    in_prog = await QuizAttemptRepository(db_session).get_in_progress(guard.id, proc.id)
    assert in_prog is not None
    links = (
        await db_session.execute(select(QuizPollLink).where(QuizPollLink.attempt_id == in_prog.id))
    ).scalars().all()
    assert links == []


# ── guard_start_quiz endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_start_creates_attempt_for_authed_guard(db_session, monkeypatch):
    fake = _fake_bot()
    monkeypatch.setattr(quiz_sender, "get_bot", lambda: fake)
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)

    result = await guard_start_quiz(proc.id, guard, db_session)
    assert result == {"started": True}
    assert fake.send_poll_calls == 1
    in_prog = await QuizAttemptRepository(db_session).get_in_progress(guard.id, proc.id)
    assert in_prog is not None
    assert in_prog.user_id == guard.id


@pytest.mark.asyncio
async def test_web_start_twice_supersedes_one_active_attempt(db_session, monkeypatch):
    """Double web start: exactly one IN_PROGRESS attempt; the poll is resent. [EDGE C2]"""
    fake = _fake_bot()
    monkeypatch.setattr(quiz_sender, "get_bot", lambda: fake)
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)

    await guard_start_quiz(proc.id, guard, db_session)
    await guard_start_quiz(proc.id, guard, db_session)

    in_progress = (
        await db_session.execute(
            select(QuizAttempt).where(
                QuizAttempt.user_id == guard.id,
                QuizAttempt.procedure_id == proc.id,
                QuizAttempt.status == "in_progress",
            )
        )
    ).scalars().all()
    assert len(in_progress) == 1
    # a poll was sent on each start (the second start resends the first question)
    assert fake.send_poll_calls == 2


@pytest.mark.asyncio
async def test_web_start_draft_is_404(db_session):
    proc = Procedure(title="טיוטה", body_text="x", status=ProcedureStatus.DRAFT)
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    guard = await _guard(db_session)
    with pytest.raises(HTTPException) as exc:
        await guard_start_quiz(proc.id, guard, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_web_start_archived_is_404(db_session):
    proc = Procedure(title="ישן", body_text="x", status=ProcedureStatus.ARCHIVED)
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    guard = await _guard(db_session)
    with pytest.raises(HTTPException) as exc:
        await guard_start_quiz(proc.id, guard, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_web_start_unknown_id_is_404(db_session):
    guard = await _guard(db_session)
    with pytest.raises(HTTPException) as exc:
        await guard_start_quiz(uuid.uuid4(), guard, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_web_start_empty_bank_is_409(db_session):
    """PUBLISHED procedure with no active questions → 409. [EDGE D1]"""
    proc = Procedure(title="ריק", body_text="x", status=ProcedureStatus.PUBLISHED)
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    guard = await _guard(db_session)
    with pytest.raises(HTTPException) as exc:
        await guard_start_quiz(proc.id, guard, db_session)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_web_start_bot_none_is_503_state_consistent(db_session, monkeypatch):
    """Bot unavailable → 503; the attempt is persisted (retry safely supersedes)
    and no orphaned poll link is left behind. [EDGE I1]"""
    monkeypatch.setattr(quiz_sender, "get_bot", lambda: None)
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)

    result = await guard_start_quiz(proc.id, guard, db_session)
    # 503 returned as a JSONResponse (not a raised HTTPException) so the attempt
    # commit above is not rolled back.
    assert getattr(result, "status_code", None) == 503

    # exactly one IN_PROGRESS attempt, no poll links → consistent state
    in_progress = (
        await db_session.execute(
            select(QuizAttempt).where(
                QuizAttempt.user_id == guard.id,
                QuizAttempt.procedure_id == proc.id,
                QuizAttempt.status == "in_progress",
            )
        )
    ).scalars().all()
    assert len(in_progress) == 1
    links = (await db_session.execute(select(QuizPollLink))).scalars().all()
    assert links == []
