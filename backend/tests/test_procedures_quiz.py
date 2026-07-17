"""
Quiz flow — the heart of the feature.

Covers: ``min(quiz_size, active_count)`` sampling, the shuffled poll→correct
mapping (QuizPollLink), PollAnswer scoring with the 80% pass threshold, retake
re-sampling, stale/abandoned polls ignored, the double-start race via the
partial unique index, and the empty-bank guard. Pure DB logic via QuizService.
"""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock

from app.exceptions import ValidationException
from app.models.user import User
from app.procedures.constants import AttemptStatus, ProcedureStatus, QuestionSource
from app.procedures.models import Procedure, QuizQuestion
from app.procedures.repositories import (
    ProcedureRepository,
    QuizAttemptRepository,
    QuizPollLinkRepository,
    QuizQuestionRepository,
)
from app.procedures.services.quiz_service import QuizService
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.settings_service import SettingsService


def _quiz(db_session) -> QuizService:
    return QuizService(
        ProcedureRepository(db_session),
        QuizQuestionRepository(db_session),
        QuizAttemptRepository(db_session),
        QuizPollLinkRepository(db_session),
        SettingsService(SystemSettingsRepository(db_session)),
    )


async def _published(db_session, n_questions=7) -> Procedure:
    proc = Procedure(title="נהל", body_text="תוכן", status=ProcedureStatus.PUBLISHED)
    db_session.add(proc)
    await db_session.flush()
    for i in range(n_questions):
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


async def _guard(db_session) -> User:
    user = User(
        phone_number="0501234567", first_name="ג", last_name="ב", roles=[],
        telegram_id="111",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _drive(quiz_service, attempt, *, correct_flags):
    """Walk the send→answer loop, answering each question correct/incorrect per
    ``correct_flags``. Returns the final AnswerOutcome (or None)."""
    answered = 0
    q = await quiz_service.current_question(attempt)
    while q is not None:
        poll_id = f"poll-{answered}"
        await quiz_service.record_poll_link(
            attempt_id=attempt.id, question_id=q.question_id,
            telegram_poll_id=poll_id, option_order=q.option_order,
            correct_option_id=q.correct_option_id,
        )
        if correct_flags[answered]:
            chosen = q.correct_option_id
        else:
            chosen = (q.correct_option_id + 1) % len(q.options)
        outcome = await quiz_service.record_answer(poll_id, chosen)
        answered += 1
        if outcome.finished:
            return outcome
        attempt = await quiz_service.next_question_attempt(outcome.attempt_id)
        q = await quiz_service.current_question(attempt)
    return None


# ── Sampling ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n_active,expected", [(3, 3), (7, 7), (10, 7)])
async def test_sampling_uses_min_quiz_size_active_count(db_session, n_active, expected):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=n_active)
    guard = await _guard(db_session)
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    assert start.created is True
    assert start.attempt.total_count == expected
    assert len(start.attempt.question_ids) == expected


async def test_start_attempt_abandons_previous_in_progress(db_session):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=7)
    guard = await _guard(db_session)
    first = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    second = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    assert second.created is True
    # the first attempt was superseded
    fresh_first = await quiz._attempts.get_by_id(first.attempt.id)
    assert fresh_first.status == AttemptStatus.ABANDONED


# ── Poll mapping + correctness ───────────────────────────────────────────────


async def test_current_question_correct_option_maps_to_correct_answer(db_session):
    """Whatever the shuffle, correct_option_id points at the correct answer text."""
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=1)
    guard = await _guard(db_session)
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    q = await quiz.current_question(start.attempt)
    # fetch the original question to know its correct text
    from app.procedures.models import QuizQuestion
    import uuid

    original = await db_session.get(QuizQuestion, uuid.UUID(q.question_id))
    assert q.options[q.correct_option_id] == original.options[original.correct_index]
    # option_order maps shown position back to the original index
    assert q.option_order[q.correct_option_id] == original.correct_index


async def test_record_answer_marks_correct_and_records_selected(db_session):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=1)
    guard = await _guard(db_session)
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    q = await quiz.current_question(start.attempt)
    await quiz.record_poll_link(
        attempt_id=start.attempt.id, question_id=q.question_id,
        telegram_poll_id="poll1", option_order=q.option_order,
        correct_option_id=q.correct_option_id,
    )
    outcome = await quiz.record_answer("poll1", q.correct_option_id)
    assert outcome.known is True
    assert outcome.finished is True  # 1 question
    assert outcome.passed is True
    attempt = await quiz._attempts.get_by_id(start.attempt.id)
    # answers recorded with original selected index + correct flag
    recorded = list(attempt.answers.values())[0]
    assert recorded["correct"] is True
    assert recorded["selected"] == q.option_order[q.correct_option_id]


# ── Scoring: pass/fail at 80% ────────────────────────────────────────────────


async def test_quiz_pass_at_threshold(db_session):
    """6/7 = 85.7% ≥ 80 → pass."""
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=7)
    guard = await _guard(db_session)
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    outcome = await _drive(quiz, start.attempt, correct_flags=[True] * 6 + [False])
    await db_session.commit()
    assert outcome.finished is True
    assert outcome.correct_count == 6
    assert outcome.score_pct == 86
    assert outcome.passed is True
    attempt = await quiz._attempts.get_by_id(start.attempt.id)
    assert attempt.status == AttemptStatus.FINISHED


async def test_quiz_fail_below_threshold(db_session):
    """5/7 = 71% < 80 → fail."""
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=7)
    guard = await _guard(db_session)
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    outcome = await _drive(quiz, start.attempt, correct_flags=[True] * 5 + [False, False])
    await db_session.commit()
    assert outcome.passed is False
    assert outcome.score_pct == 71
    assert outcome.threshold == 80  # carried for the configurable fail message


async def test_threshold_boundary_eighty_passes(db_session):
    """4/5 = 80% exactly → pass (≥ threshold)."""
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=5)
    guard = await _guard(db_session)
    # set quiz_size up to 5 so all 5 are sampled
    from app.repositories.system_settings_repository import SystemSettingsRepository
    from app.services.settings_service import SettingsService

    await SettingsService(SystemSettingsRepository(db_session))._settings_repo.set(
        "procedure_quiz_size", "5"
    )
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    assert start.attempt.total_count == 5
    outcome = await _drive(quiz, start.attempt, correct_flags=[True] * 4 + [False])
    await db_session.commit()
    assert outcome.score_pct == 80
    assert outcome.passed is True


# ── Retake ───────────────────────────────────────────────────────────────────


async def test_retake_creates_fresh_attempt(db_session):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=7)
    guard = await _guard(db_session)
    first = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    outcome = await _drive(quiz, first.attempt, correct_flags=[False] * 7)  # fail
    await db_session.commit()
    assert outcome.passed is False

    retake = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    assert retake.created is True
    assert retake.attempt.id != first.attempt.id
    assert retake.attempt.status == AttemptStatus.IN_PROGRESS
    # the failed attempt stays FINISHED (a fresh sample is the new attempt)
    failed = await quiz._attempts.get_by_id(first.attempt.id)
    assert failed.status == AttemptStatus.FINISHED


# ── Stale / abandoned / unknown polls ────────────────────────────────────────


async def test_unknown_poll_ignored(db_session):
    quiz = _quiz(db_session)
    outcome = await quiz.record_answer("does-not-exist", 0)
    assert outcome.known is False


async def test_abandoned_attempt_poll_ignored(db_session):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=2)
    guard = await _guard(db_session)
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    q = await quiz.current_question(start.attempt)
    await quiz.record_poll_link(
        attempt_id=start.attempt.id, question_id=q.question_id,
        telegram_poll_id="p1", option_order=q.option_order,
        correct_option_id=q.correct_option_id,
    )
    # abandon the attempt (a newer one superseded it)
    await quiz._attempts.abandon_in_progress(guard.id, proc.id)
    await db_session.commit()
    outcome = await quiz.record_answer("p1", q.correct_option_id)
    assert outcome.known is False  # abandoned → ignored


async def test_double_answer_is_idempotent(db_session):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=2)
    guard = await _guard(db_session)
    start = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    q = await quiz.current_question(start.attempt)
    await quiz.record_poll_link(
        attempt_id=start.attempt.id, question_id=q.question_id,
        telegram_poll_id="p1", option_order=q.option_order,
        correct_option_id=q.correct_option_id,
    )
    first = await quiz.record_answer("p1", q.correct_option_id)
    assert first.known is True and first.finished is False
    second = await quiz.record_answer("p1", q.correct_option_id)
    assert second.already_recorded is True


# ── Double-start race via the partial unique index ──────────────────────────


async def test_double_start_race_returns_surviving_attempt(db_session, monkeypatch):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=7)
    guard = await _guard(db_session)
    first = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()

    # Simulate a concurrent tap: the abandon step is a no-op so the committed
    # IN_PROGRESS attempt survives, and the second INSERT hits the unique index.
    monkeypatch.setattr(
        quiz._attempts, "abandon_in_progress", AsyncMock(return_value=0)
    )
    second = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    assert second.created is False
    assert second.attempt.id == first.attempt.id  # rejoined the survivor


async def test_race_with_outstanding_poll_has_flag(db_session, monkeypatch):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=7)
    guard = await _guard(db_session)
    first = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    # send question 1 (create its poll link, unanswered)
    q = await quiz.current_question(first.attempt)
    await quiz.record_poll_link(
        attempt_id=first.attempt.id, question_id=q.question_id,
        telegram_poll_id="p1", option_order=q.option_order,
        correct_option_id=q.correct_option_id,
    )
    await db_session.commit()

    monkeypatch.setattr(
        quiz._attempts, "abandon_in_progress", AsyncMock(return_value=0)
    )
    second = await quiz.start_attempt(guard.id, proc.id)
    await db_session.commit()
    # the surviving attempt has an outstanding (unanswered) poll → no-op signal
    assert await quiz.has_outstanding_poll(second.attempt) is True


# ── Empty bank ───────────────────────────────────────────────────────────────


async def test_start_attempt_empty_bank_raises(db_session):
    quiz = _quiz(db_session)
    proc = await _published(db_session, n_questions=0)
    guard = await _guard(db_session)
    with pytest.raises(ValidationException):
        await quiz.start_attempt(guard.id, proc.id)


async def test_start_attempt_not_published_raises(db_session):
    quiz = _quiz(db_session)
    proc = Procedure(title="נהל", body_text="תוכן", status=ProcedureStatus.DRAFT)
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    guard = await _guard(db_session)
    with pytest.raises(ValidationException):
        await quiz.start_attempt(guard.id, proc.id)
