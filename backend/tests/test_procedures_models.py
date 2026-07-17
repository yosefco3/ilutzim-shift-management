"""
Procedure-quiz models — table shape, enum storage, and the partial unique index
that backs the double-"start quiz" race protection.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.procedures.constants import (
    AttemptStatus,
    ProcedureStatus,
    QuestionSource,
)
from app.procedures.models import (
    Procedure,
    QuizAttempt,
    QuizPollLink,
    QuizQuestion,
)


async def _procedure(db_session, *, status=ProcedureStatus.DRAFT) -> Procedure:
    proc = Procedure(title="נהל כניסה", body_text="תוכן", status=status)
    db_session.add(proc)
    await db_session.flush()
    return proc


async def _user(db_session):
    from app.models.user import User

    user = User(phone_number="0501234567", first_name="יוסי", last_name="כהן", roles=[])
    db_session.add(user)
    await db_session.flush()
    return user


async def test_procedure_defaults_and_status(db_session):
    proc = await _procedure(db_session)
    assert proc.status == ProcedureStatus.DRAFT
    assert proc.published_at is None
    assert proc.is_default is False  # a fresh procedure is never the default
    await db_session.commit()
    fresh = await db_session.get(Procedure, proc.id)
    assert fresh.status == ProcedureStatus.DRAFT
    assert fresh.is_default is False


@pytest.mark.parametrize("first_default,second_default,should_block", [
    (True, True, True),    # two defaults → blocked by the partial unique index
    (True, False, False),  # a default + a non-default coexist
    (False, True, False),
    (False, False, False), # many non-defaults are fine
])
async def test_partial_unique_index_single_default(
    db_session, first_default, second_default, should_block
):
    """At most one procedure may be the default (the partial index backstop)."""
    a = Procedure(title="א", body_text="תוכן", is_default=first_default)
    db_session.add(a)
    await db_session.flush()

    b = Procedure(title="ב", body_text="תוכן", is_default=second_default)
    db_session.add(b)
    if should_block:
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()
    else:
        await db_session.flush()


async def test_question_source_and_options_json(db_session):
    proc = await _procedure(db_session)
    q = QuizQuestion(
        procedure_id=proc.id,
        text="מה עושים?",
        options=["א", "ב", "ג", "ד"],
        correct_index=2,
        display_order=0,
        is_active=True,
        source=QuestionSource.AI,
    )
    db_session.add(q)
    await db_session.commit()
    fresh = await db_session.get(QuizQuestion, q.id)
    assert fresh.options == ["א", "ב", "ג", "ד"]
    assert fresh.correct_index == 2
    assert fresh.source == QuestionSource.AI
    assert fresh.edited_at is None


async def test_quiz_poll_link_string_primary_key(db_session):
    proc = await _procedure(db_session)
    user = await _user(db_session)
    attempt = QuizAttempt(
        procedure_id=proc.id,
        user_id=user.id,
        question_ids=["q1"],
        answers={},
        started_at=datetime.now(timezone.utc),
        total_count=1,
    )
    db_session.add(attempt)
    await db_session.flush()
    q = QuizQuestion(
        procedure_id=proc.id, text="q", options=["a", "b"],
        correct_index=0, display_order=0,
    )
    db_session.add(q)
    await db_session.flush()
    link = QuizPollLink(
        telegram_poll_id="poll123",
        attempt_id=attempt.id,
        question_id=q.id,
        option_order=[1, 0],
        correct_option_id=1,
    )
    db_session.add(link)
    await db_session.commit()
    fresh = await db_session.get(QuizPollLink, "poll123")
    assert fresh is not None
    assert fresh.correct_option_id == 1


@pytest.mark.parametrize("first_status,second_status,should_block", [
    (AttemptStatus.IN_PROGRESS, AttemptStatus.IN_PROGRESS, True),
    (AttemptStatus.FINISHED, AttemptStatus.IN_PROGRESS, False),
    (AttemptStatus.IN_PROGRESS, AttemptStatus.FINISHED, False),
    (AttemptStatus.ABANDONED, AttemptStatus.IN_PROGRESS, False),
])
async def test_partial_unique_index_one_in_progress(
    db_session, first_status, second_status, should_block
):
    """At most one IN_PROGRESS attempt per (user, procedure); other statuses coexist."""
    proc = await _procedure(db_session)
    user = await _user(db_session)
    now = datetime.now(timezone.utc)

    a1 = QuizAttempt(
        procedure_id=proc.id, user_id=user.id, question_ids=["q1"], answers={},
        started_at=now, total_count=1, status=first_status,
    )
    db_session.add(a1)
    await db_session.flush()

    a2 = QuizAttempt(
        procedure_id=proc.id, user_id=user.id, question_ids=["q2"], answers={},
        started_at=now, total_count=1, status=second_status,
    )
    db_session.add(a2)
    if should_block:
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()
    else:
        await db_session.flush()


async def test_attempt_for_different_users_coexist(db_session):
    """Two IN_PROGRESS attempts for the SAME procedure but DIFFERENT users are fine."""
    proc = await _procedure(db_session)
    u1 = await _user(db_session)
    from app.models.user import User

    u2 = User(phone_number="0509999999", first_name="דנה", last_name="לוי", roles=[])
    db_session.add(u2)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(QuizAttempt(
        procedure_id=proc.id, user_id=u1.id, question_ids=["q1"], answers={},
        started_at=now, total_count=1, status=AttemptStatus.IN_PROGRESS,
    ))
    db_session.add(QuizAttempt(
        procedure_id=proc.id, user_id=u2.id, question_ids=["q1"], answers={},
        started_at=now, total_count=1, status=AttemptStatus.IN_PROGRESS,
    ))
    await db_session.commit()  # no IntegrityError
