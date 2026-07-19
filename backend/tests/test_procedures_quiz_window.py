"""
Quiz availability window — pure helper matrix, the single start gate, mid-flight
immunity, and the reminder skip. [quiz_availability_window EDGE T1–T3, C1, D3]
"""

from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock

from app.exceptions import ValidationException
from app.procedures.constants import ProcedureStatus
from app.procedures.dependencies import build_quiz_service
from app.procedures.models import Procedure
from app.procedures.repositories import (
    ProcedureRepository,
    QuizAttemptRepository,
    ProcedureReminderRepository,
)
from app.procedures.services.quiz_window import is_quiz_open, quiz_deadline
from app.procedures.services.reminder_service import ProcedureReminderService
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.utils.date_utils import now_il

from tests.test_procedures_quiz_start import _guard, _published_with_questions

_NOW = datetime(2026, 7, 19, 12, 0, 0)


def _proc(anchor=None, published=None) -> Procedure:
    return Procedure(
        title="נהל", body_text="x", status=ProcedureStatus.PUBLISHED,
        published_at=published, quiz_window_started_at=anchor,
    )


# ── Pure helper matrix ───────────────────────────────────────────────────────


def test_window_zero_means_unlimited():
    proc = _proc(anchor=_NOW - timedelta(days=365))
    assert quiz_deadline(proc, 0) is None
    assert is_quiz_open(proc, 0, _NOW) is True


def test_no_anchor_and_no_published_at_is_open():
    """Legacy safety: both stamps None → never locked out. [EDGE T2]"""
    assert is_quiz_open(_proc(), 1, _NOW) is True


def test_open_inside_window_and_closed_after():
    proc = _proc(anchor=_NOW - timedelta(days=2))
    assert is_quiz_open(proc, 3, _NOW) is True
    assert is_quiz_open(proc, 1, _NOW) is False
    assert quiz_deadline(proc, 3) == proc.quiz_window_started_at + timedelta(days=3)


def test_anchor_falls_back_to_published_at():
    """Rows published before the migration measure from published_at. [EDGE T2]"""
    proc = _proc(anchor=None, published=_NOW - timedelta(days=2))
    assert is_quiz_open(proc, 1, _NOW) is False
    assert is_quiz_open(proc, 3, _NOW) is True


# ── The start gate (single enforcement point) ────────────────────────────────


async def _set_window(db_session, days: str) -> None:
    await SystemSettingsRepository(db_session).set(
        "procedure_quiz_window_days", days
    )
    await db_session.commit()


async def _expire(db_session, proc, days=2) -> None:
    proc.quiz_window_started_at = now_il().replace(tzinfo=None) - timedelta(days=days)
    await db_session.commit()


@pytest.mark.asyncio
async def test_start_blocked_when_window_expired(db_session):
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    await _set_window(db_session, "1")
    await _expire(db_session, proc, days=2)

    svc = build_quiz_service(db_session)
    with pytest.raises(ValidationException) as exc_info:
        await svc.start_attempt(guard.id, proc.id)
    assert "לא זמין" in exc_info.value.message
    assert await QuizAttemptRepository(db_session).get_any_in_progress(guard.id) is None


@pytest.mark.asyncio
async def test_start_allowed_inside_window(db_session):
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    await _set_window(db_session, "1")
    proc.quiz_window_started_at = now_il().replace(tzinfo=None) - timedelta(hours=1)
    await db_session.commit()

    svc = build_quiz_service(db_session)
    assert (await svc.start_attempt(guard.id, proc.id)).created is True


@pytest.mark.asyncio
async def test_start_allowed_when_setting_zero_even_if_old(db_session):
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    await _set_window(db_session, "0")
    await _expire(db_session, proc, days=365)

    svc = build_quiz_service(db_session)
    assert (await svc.start_attempt(guard.id, proc.id)).created is True


@pytest.mark.asyncio
async def test_open_attempt_survives_expiry_midflight(db_session):
    """The gate is start-only: an IN_PROGRESS attempt keeps flowing. [EDGE T3]"""
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    svc = build_quiz_service(db_session)
    started = await svc.start_attempt(guard.id, proc.id)

    await _set_window(db_session, "1")
    await _expire(db_session, proc, days=2)

    # Mid-quiz operations still work — only a NEW start is refused.
    question = await svc.current_question(started.attempt)
    assert question is not None
    with pytest.raises(ValidationException):
        await svc.start_attempt(guard.id, proc.id)


# ── API surface: guard_view + admin list expose the window [EDGE U1, U2] ────


def _procedure_service(db_session):
    from unittest.mock import AsyncMock as _AsyncMock

    from app.procedures.repositories.question_repository import (
        QuizQuestionRepository,
    )
    from app.procedures.services.procedure_service import ProcedureService
    from app.services.settings_service import SettingsService

    return ProcedureService(
        ProcedureRepository(db_session),
        QuizQuestionRepository(db_session),
        QuizAttemptRepository(db_session),
        UserRepository(db_session),
        SettingsService(SystemSettingsRepository(db_session)),
        _AsyncMock(),  # publisher — unused here
    )


@pytest.mark.asyncio
async def test_guard_view_reports_quiz_closed(db_session):
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    await _set_window(db_session, "1")
    await _expire(db_session, proc, days=2)

    view = await _procedure_service(db_session).guard_view(proc.id, guard)
    assert view["quiz_open"] is False
    assert view["body_text"]  # reading payload untouched — only the quiz closes


@pytest.mark.asyncio
async def test_guard_view_reports_quiz_open_at_default_setting(db_session):
    proc = await _published_with_questions(db_session)
    guard = await _guard(db_session)
    view = await _procedure_service(db_session).guard_view(proc.id, guard)
    assert view["quiz_open"] is True


@pytest.mark.asyncio
async def test_list_all_exposes_window_state(db_session):
    proc = await _published_with_questions(db_session)
    await _set_window(db_session, "1")
    await _expire(db_session, proc, days=2)

    rows = await _procedure_service(db_session).list_all()
    row = next(r for r in rows if r["id"] == proc.id)
    assert row["quiz_open"] is False
    assert row["quiz_deadline_at"] == proc.quiz_window_started_at + timedelta(days=1)


@pytest.mark.asyncio
async def test_list_all_unlimited_window_has_no_deadline(db_session):
    proc = await _published_with_questions(db_session)
    rows = await _procedure_service(db_session).list_all()
    row = next(r for r in rows if r["id"] == proc.id)
    assert row["quiz_open"] is True
    assert row["quiz_deadline_at"] is None


# ── Reminder skip [EDGE D3] ─────────────────────────────────────────────────


async def _reminder_svc(db_session, send):
    return ProcedureReminderService(
        ProcedureRepository(db_session),
        QuizAttemptRepository(db_session),
        ProcedureReminderRepository(db_session),
        UserRepository(db_session),
        send,
    )


@pytest.mark.asyncio
async def test_reminder_skipped_when_window_expired(db_session):
    now = now_il().replace(tzinfo=None)
    old = now - timedelta(days=3)
    proc = Procedure(
        title="נהל", body_text="x", status=ProcedureStatus.PUBLISHED,
        published_at=old, quiz_window_started_at=old, is_default=True,
    )
    db_session.add(proc)
    await db_session.commit()
    await _guard(db_session)

    send = AsyncMock(return_value=True)
    svc = await _reminder_svc(db_session, send)
    assert await svc.run(now, window_days=1) == 0
    send.assert_not_awaited()
    # Same state, unlimited window → the reminder goes out.
    assert await svc.run(now, window_days=0) == 1
