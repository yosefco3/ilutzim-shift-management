"""
Procedure reminder job — idempotency, the 48h age gate, pass exclusion, and the
reinforcement exclusion. Uses a fake ``send`` so no bot is involved.
"""

from datetime import timedelta

import pytest
from unittest.mock import AsyncMock

from app.models.user import User
from app.procedures.constants import AttemptStatus, ProcedureStatus, REMINDER_AGE_HOURS
from app.procedures.models import Procedure, QuizAttempt
from app.procedures.repositories import (
    ProcedureRepository,
    QuizAttemptRepository,
    ProcedureReminderRepository,
)
from app.procedures.services.reminder_service import ProcedureReminderService
from app.repositories.user_repository import UserRepository
from app.utils.date_utils import now_il


def _service(db_session, send=None):
    return ProcedureReminderService(
        ProcedureRepository(db_session),
        QuizAttemptRepository(db_session),
        ProcedureReminderRepository(db_session),
        UserRepository(db_session),
        send or AsyncMock(return_value=True),
    )


async def _old_procedure(db_session, *, hours_old=REMINDER_AGE_HOURS + 1):
    published = now_il().replace(tzinfo=None) - timedelta(hours=hours_old)
    # The reminder targets ONLY the default procedure, so the fixture flags it.
    proc = Procedure(
        title="נהל ישן", body_text="תוכן", status=ProcedureStatus.PUBLISHED,
        published_at=published, is_default=True,
    )
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    return proc


async def _guard(db_session, telegram_id="111"):
    user = User(
        phone_number=f"050{telegram_id[-7:]}", first_name="ג", last_name="ב",
        roles=[], telegram_id=telegram_id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_reminder_sent_once_then_idempotent(db_session):
    send = AsyncMock(return_value=True)
    svc = _service(db_session, send)
    proc = await _old_procedure(db_session)
    guard = await _guard(db_session)

    now = now_il().replace(tzinfo=None)
    assert await svc.run(now) == 1
    assert send.await_count == 1
    # second run → already recorded → no duplicate
    assert await svc.run(now) == 0
    assert send.await_count == 1


async def test_reminder_skips_recently_published(db_session):
    send = AsyncMock(return_value=True)
    svc = _service(db_session, send)
    # Default procedure, but published only 2h ago → below the 48h age gate.
    proc = Procedure(title="חדש", body_text="תוכן", status=ProcedureStatus.PUBLISHED,
                     published_at=now_il().replace(tzinfo=None) - timedelta(hours=2),
                     is_default=True)
    db_session.add(proc)
    await db_session.commit()
    await _guard(db_session)
    assert await svc.run(now_il().replace(tzinfo=None)) == 0
    assert send.await_count == 0


async def test_reminder_ignores_non_default_published_procedures(db_session):
    """An old, published, non-default procedure is NOT reminded about."""
    send = AsyncMock(return_value=True)
    svc = _service(db_session, send)
    published = now_il().replace(tzinfo=None) - timedelta(hours=REMINDER_AGE_HOURS + 1)
    # Old + published + not passed, but NOT the default → ignored.
    proc = Procedure(
        title="נהל אחר", body_text="תוכן", status=ProcedureStatus.PUBLISHED,
        published_at=published, is_default=False,
    )
    db_session.add(proc)
    await db_session.commit()
    await _guard(db_session)
    assert await svc.run(now_il().replace(tzinfo=None)) == 0
    assert send.await_count == 0


async def test_reminder_nothing_when_there_is_no_default(db_session):
    """No default procedure at all → no reminders, even for old published ones."""
    send = AsyncMock(return_value=True)
    svc = _service(db_session, send)
    published = now_il().replace(tzinfo=None) - timedelta(hours=REMINDER_AGE_HOURS + 1)
    db_session.add(Procedure(
        title="נהל ישן", body_text="תוכן", status=ProcedureStatus.PUBLISHED,
        published_at=published,  # not default
    ))
    await db_session.commit()
    await _guard(db_session)
    assert await svc.run(now_il().replace(tzinfo=None)) == 0
    assert send.await_count == 0


async def test_reminder_skips_guards_who_passed(db_session):
    send = AsyncMock(return_value=True)
    svc = _service(db_session, send)
    proc = await _old_procedure(db_session)
    guard = await _guard(db_session)
    db_session.add(QuizAttempt(
        procedure_id=proc.id, user_id=guard.id, question_ids=[], answers={},
        started_at=now_il().replace(tzinfo=None), total_count=7, correct_count=7,
        passed=True, status=AttemptStatus.FINISHED,
    ))
    await db_session.commit()
    assert await svc.run(now_il().replace(tzinfo=None)) == 0
    assert send.await_count == 0


async def test_reminder_excludes_reinforcement(db_session):
    send = AsyncMock(return_value=True)
    svc = _service(db_session, send)
    proc = await _old_procedure(db_session)
    # reinforcement guard — never a reminder recipient
    db_session.add(User(
        phone_number="0500000999", first_name="מתגבר", last_name="ח",
        roles=[], telegram_id="999", is_reinforcement=True,
    ))
    await db_session.commit()
    assert await svc.run(now_il().replace(tzinfo=None)) == 0
    assert send.await_count == 0


async def test_reminder_records_row_before_send(db_session):
    """Crash-safe: the ledger row exists even if the send is inspected after."""
    send = AsyncMock(return_value=True)
    svc = _service(db_session, send)
    proc = await _old_procedure(db_session)
    guard = await _guard(db_session)
    now = now_il().replace(tzinfo=None)
    await svc.run(now)
    exists = await svc._reminders.exists(proc.id, guard.id)
    assert exists is True
