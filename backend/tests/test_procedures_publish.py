"""
Publish flow: quiz_size gate, 409 on re-publish, real counts via the publisher
seam, rebroadcast skips guards who already passed, and reinforcement exclusion.
"""

from datetime import datetime, timezone

import pytest

from app.exceptions import ConflictException, ValidationException
from app.models.user import User
from app.procedures.constants import AttemptStatus, ProcedureStatus, QuestionSource
from app.procedures.models import Procedure, QuizAttempt, QuizQuestion
from app.procedures.repositories import (
    ProcedureRepository,
    QuizAttemptRepository,
    QuizQuestionRepository,
)
from app.procedures.services.procedure_service import ProcedureService
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.services.settings_service import SettingsService


class _FakePublisher:
    def __init__(self):
        self.calls = []

    async def broadcast(self, recipients, title, procedure_id):
        self.calls.append(list(recipients))
        return {"sent": len(recipients), "skipped": 0, "total": len(recipients)}


def _svc(db_session, publisher=None) -> ProcedureService:
    return ProcedureService(
        ProcedureRepository(db_session),
        QuizQuestionRepository(db_session),
        QuizAttemptRepository(db_session),
        UserRepository(db_session),
        SettingsService(SystemSettingsRepository(db_session)),
        publisher or _FakePublisher(),
    )


async def _make_proc(db_session, n_active=7, status=ProcedureStatus.DRAFT) -> Procedure:
    proc = Procedure(title="נהל כניסה", body_text="תוכן ארוך " * 50, status=status)
    db_session.add(proc)
    await db_session.flush()
    for i in range(n_active):
        db_session.add(
            QuizQuestion(
                procedure_id=proc.id, text=f"שאלה {i}",
                options=["א", "ב", "ג", "ד"], correct_index=0,
                display_order=i, source=QuestionSource.AI,
            )
        )
    await db_session.commit()
    await db_session.refresh(proc)
    return proc


async def _guard(db_session, telegram_id="111", reinforcement=False) -> User:
    user = User(
        phone_number=f"050{telegram_id[-7:]}",
        first_name="ג", last_name="ב", roles=[],
        telegram_id=telegram_id, is_reinforcement=reinforcement,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_publish_requires_min_active_questions(db_session):
    svc = _svc(db_session)
    proc = await _make_proc(db_session, n_active=6)  # default quiz_size = 7
    with pytest.raises(ValidationException):
        await svc.publish(proc.id)


async def test_publish_broadcasts_to_all_recipients_with_counts(db_session):
    pub = _FakePublisher()
    svc = _svc(db_session, pub)
    proc = await _make_proc(db_session, n_active=7)
    organic = await _guard(db_session, "111")
    await _guard(db_session, "222", reinforcement=True)  # excluded

    summary = await svc.publish(proc.id)
    assert summary == {"sent": 1, "skipped": 0, "total": 1, "republished": False}
    assert pub.calls == [["111"]]  # reinforcement guard excluded

    # status + published_at stamped
    fresh = await svc._procedures.get_by_id(proc.id)
    assert fresh.status == ProcedureStatus.PUBLISHED
    assert fresh.published_at is not None


async def test_publish_again_without_rebroadcast_is_409(db_session):
    svc = _svc(db_session)
    proc = await _make_proc(db_session, n_active=7)
    await _guard(db_session, "111")
    await svc.publish(proc.id)
    with pytest.raises(ConflictException):
        await svc.publish(proc.id)


async def test_publish_skips_guard_without_telegram(db_session):
    pub = _FakePublisher()
    svc = _svc(db_session, pub)
    proc = await _make_proc(db_session, n_active=7)
    db_session.add(User(
        phone_number="0500000000", first_name="x", last_name="y", roles=[],
        telegram_id=None,
    ))
    await db_session.commit()
    summary = await svc.publish(proc.id)
    assert summary["total"] == 0
    assert pub.calls == [[]]


async def test_rebroadcast_skips_guards_who_passed(db_session):
    pub = _FakePublisher()
    svc = _svc(db_session, pub)
    proc = await _make_proc(db_session, n_active=7)
    guard = await _guard(db_session, "111")

    # first publish → broadcasts to the one guard
    await svc.publish(proc.id)
    assert pub.calls == [["111"]]

    # record a passed attempt for the guard
    db_session.add(QuizAttempt(
        procedure_id=proc.id, user_id=guard.id, question_ids=[str(guard.id)],
        answers={}, started_at=datetime.now(timezone.utc),
        total_count=7, correct_count=7, passed=True, status=AttemptStatus.FINISHED,
    ))
    await db_session.commit()

    # rebroadcast → guard already passed → excluded (no redundant noise)
    summary = await svc.publish(proc.id, rebroadcast=True)
    assert summary["republished"] is True
    assert pub.calls[-1] == []  # passed guard skipped


async def test_rebroadcast_still_reaches_non_passers(db_session):
    pub = _FakePublisher()
    svc = _svc(db_session, pub)
    proc = await _make_proc(db_session, n_active=7)
    passer = await _guard(db_session, "111")
    other = await _guard(db_session, "222")
    await svc.publish(proc.id)
    db_session.add(QuizAttempt(
        procedure_id=proc.id, user_id=passer.id, question_ids=[], answers={},
        started_at=datetime.now(timezone.utc), total_count=7, correct_count=7,
        passed=True, status=AttemptStatus.FINISHED,
    ))
    await db_session.commit()
    summary = await svc.publish(proc.id, rebroadcast=True)
    assert summary["sent"] == 1
    assert pub.calls[-1] == ["222"]


async def test_first_publish_makes_procedure_the_default(db_session):
    svc = _svc(db_session)
    proc = await _make_proc(db_session, n_active=7)
    assert proc.is_default is False
    await svc.publish(proc.id)
    fresh = await svc._procedures.get_by_id(proc.id)
    assert fresh.is_default is True


async def test_publish_moves_default_and_clears_previous(db_session):
    """Publishing a second procedure clears the old default (single default)."""
    svc = _svc(db_session)
    first = await _make_proc(db_session, n_active=7)
    second = await _make_proc(db_session, n_active=7)

    await svc.publish(first.id)
    assert (await svc._procedures.get_by_id(first.id)).is_default is True
    assert (await svc._procedures.get_by_id(second.id)).is_default is False

    await svc.publish(second.id)
    # second is now the default; first's default flag is cleared (atomically)
    assert (await svc._procedures.get_by_id(second.id)).is_default is True
    assert (await svc._procedures.get_by_id(first.id)).is_default is False
    # exactly one default overall
    default = await svc._procedures.get_default()
    assert default is not None and default.id == second.id


async def test_rebroadcast_reselects_default(db_session):
    """Re-broadcast re-selects the default and clears the previous one."""
    svc = _svc(db_session)
    proc = await _make_proc(db_session, n_active=7)
    other = await _make_proc(db_session, n_active=7)

    # other becomes the default first, then proc is published (default→proc)
    await svc.publish(other.id)
    await svc.publish(proc.id)
    assert (await svc._procedures.get_by_id(proc.id)).is_default is True

    # publishing `other` again via rebroadcast moves the default back to it
    await svc.publish(other.id, rebroadcast=True)
    assert (await svc._procedures.get_by_id(other.id)).is_default is True
    assert (await svc._procedures.get_by_id(proc.id)).is_default is False
