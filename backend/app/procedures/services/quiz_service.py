"""
QuizService — the guard-facing quiz flow (pure DB logic).

The bot handler owns the aiogram sends (``send_poll`` / ``send_message``); this
service owns all the state: starting an attempt (sampling + race handling via the
partial unique index), preparing each question's shuffled options, recording a
PollAnswer idempotently, and scoring at the end. Keeping it DB-only makes the
whole flow unit-testable with just an in-memory session.

Sampling/shuffling use ``random`` so tests can monkeypatch it for determinism.
"""

import logging
import random
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.exceptions import UserNotFoundException, ValidationException
from app.procedures.constants import (
    AttemptStatus,
    ProcedureStatus,
)
from app.procedures.models.quiz_attempt import QuizAttempt
from app.procedures.repositories.attempt_repository import QuizAttemptRepository
from app.procedures.repositories.poll_link_repository import QuizPollLinkRepository
from app.procedures.repositories.procedure_repository import ProcedureRepository
from app.procedures.repositories.question_repository import QuizQuestionRepository
from app.procedures.services.quiz_window import is_quiz_open
from app.services.settings_service import SettingsService
from app.utils.date_utils import now_il

logger = logging.getLogger("ilutzim")


@dataclass
class AttemptStart:
    """Result of starting an attempt.

    ``created=False`` means a surviving IN_PROGRESS attempt was reused (the
    double-tap race): the caller must decide no-op vs resend using
    ``QuizService.has_outstanding_poll``.
    """

    attempt: QuizAttempt
    created: bool


@dataclass
class QuestionToSend:
    """A question prepared for sending: shuffled options + the poll mapping."""

    question_id: str
    text: str
    options: list[str]  # option TEXT in shuffled (shown) order
    option_order: list[int]  # shown_position -> original index
    correct_option_id: int  # shown position of the correct option


@dataclass
class AnswerOutcome:
    """Result of recording a PollAnswer."""

    known: bool  # False → unknown/stale poll or finished attempt: ignore silently
    already_recorded: bool = False
    finished: bool = False
    correct_count: int | None = None
    total_count: int | None = None
    score_pct: int | None = None
    passed: bool | None = None
    next_question_id: str | None = None  # set when not finished
    attempt_id: uuid.UUID | None = None
    procedure_id: uuid.UUID | None = None
    threshold: int | None = None  # the pass threshold used (for the fail message)


def _now_naive():
    return now_il().replace(tzinfo=None)


async def _setting_int(settings: SettingsService, key: str, default: int) -> int:
    value = await settings.get_setting(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class QuizService:
    """The sequential quiz flow: start → answer → score, snapshot-by-reference."""

    def __init__(
        self,
        procedure_repo: ProcedureRepository,
        question_repo: QuizQuestionRepository,
        attempt_repo: QuizAttemptRepository,
        poll_link_repo: QuizPollLinkRepository,
        settings: SettingsService,
    ) -> None:
        self._procedures = procedure_repo
        self._questions = question_repo
        self._attempts = attempt_repo
        self._poll_links = poll_link_repo
        self._settings = settings

    # ── Start ─────────────────────────────────────────────────────────────

    async def start_attempt(
        self, user_id: uuid.UUID, procedure_id: uuid.UUID
    ) -> AttemptStart:
        """Begin (or rejoin) a quiz attempt for a guard+procedure.

        Samples ``min(quiz_size, active_count)`` random active questions,
        supersedes any previous IN_PROGRESS attempt (ABANDONED), then INSERTs a
        new attempt. On the rare double-tap race the partial unique index makes
        the second INSERT fail; we recover and return the surviving attempt
        (``created=False``) so the caller never double-sends question 1.
        """
        proc = await self._procedures.get_by_id(procedure_id)
        if proc is None:
            raise UserNotFoundException("הנוהל לא נמצא")
        if proc.status != ProcedureStatus.PUBLISHED:
            raise ValidationException("המבחן כבר אינו פעיל")

        # Availability window: the SINGLE gate for both entry points (the bot
        # callback and the WebApp start endpoint both surface this message).
        # Start-only — an attempt already in progress may finish. [EDGE C1, T3]
        window_days = await _setting_int(
            self._settings, "procedure_quiz_window_days", 0
        )
        if not is_quiz_open(proc, window_days, _now_naive()):
            raise ValidationException(
                "המבחן כבר לא זמין — חלון הזמן לביצועו הסתיים. "
                "המנהל יכול לפרסם אותו מחדש."
            )

        active = await self._questions.list_active(procedure_id)
        if not active:
            raise ValidationException("בנק השאלות אינו זמין כעת")

        # One quiz at a time: an open attempt on a DIFFERENT procedure blocks a
        # new start (the guard finishes it or exits via the poll's exit button).
        # A same-procedure open attempt keeps the existing behavior below —
        # superseded by the fresh attempt (retake / walked-away restart).
        open_attempt = await self._attempts.get_any_in_progress(user_id)
        if open_attempt is not None and open_attempt.procedure_id != procedure_id:
            blocking = await self._procedures.get_by_id(open_attempt.procedure_id)
            blocking_title = blocking.title if blocking is not None else "נוהל אחר"
            raise ValidationException(
                f'יש לך מבחן פתוח על הנוהל "{blocking_title}" — '
                "סיים אותו או צא ממנו (כפתור היציאה מוצמד לשאלה) לפני שמתחילים מבחן חדש"
            )

        quiz_size = await _setting_int(self._settings, "procedure_quiz_size", 7)
        sample_size = min(quiz_size, len(active))
        sample = random.sample(active, sample_size)
        question_ids = [str(q.id) for q in sample]

        # Supersede any stale in-flight attempt (guard walked away mid-quiz).
        await self._attempts.abandon_in_progress(user_id, procedure_id)

        attempt = QuizAttempt(
            procedure_id=procedure_id,
            user_id=user_id,
            question_ids=question_ids,
            answers={},
            started_at=_now_naive(),
            total_count=sample_size,
            status=AttemptStatus.IN_PROGRESS,
        )
        self._attempts.session.add(attempt)
        try:
            await self._attempts.session.flush()
        except IntegrityError:
            # Race: another tap already created the IN_PROGRESS attempt. Roll
            # back our partial work and rejoin the surviving attempt.
            await self._attempts.session.rollback()
            surviving = await self._attempts.get_in_progress(user_id, procedure_id)
            if surviving is not None:
                return AttemptStart(surviving, created=False)
            # Extremely unlikely (the winner rolled back too) — retry once.
            attempt = QuizAttempt(
                procedure_id=procedure_id,
                user_id=user_id,
                question_ids=question_ids,
                answers={},
                started_at=_now_naive(),
                total_count=sample_size,
                status=AttemptStatus.IN_PROGRESS,
            )
            self._attempts.session.add(attempt)
            try:
                await self._attempts.session.flush()
            except IntegrityError:
                await self._attempts.session.rollback()
                surviving = await self._attempts.get_in_progress(user_id, procedure_id)
                if surviving is None:
                    raise
                return AttemptStart(surviving, created=False)
        return AttemptStart(attempt, created=True)

    # ── Sending one question ──────────────────────────────────────────────

    async def current_question(self, attempt: QuizAttempt) -> QuestionToSend | None:
        """Prepare the first unanswered question of the attempt for sending.

        Returns None if every sampled question is already answered.
        """
        target_qid = self._first_unanswered(attempt)
        if target_qid is None:
            return None
        question = await self._questions.get_by_id(uuid.UUID(target_qid))
        if question is None:
            return None

        indices = list(range(len(question.options)))
        random.shuffle(indices)  # indices[shown] -> original index
        shuffled = [question.options[i] for i in indices]
        correct_shown = indices.index(question.correct_index)
        return QuestionToSend(
            question_id=target_qid,
            text=question.text,
            options=shuffled,
            option_order=indices,
            correct_option_id=correct_shown,
        )

    async def record_poll_link(
        self,
        *,
        attempt_id: uuid.UUID,
        question_id: str,
        telegram_poll_id: str,
        option_order: list[int],
        correct_option_id: int,
    ) -> None:
        """Persist the mapping for a poll we just sent (so PollAnswer resolves)."""
        await self._poll_links.create(
            telegram_poll_id=telegram_poll_id,
            attempt_id=attempt_id,
            question_id=uuid.UUID(question_id),
            option_order=option_order,
            correct_option_id=correct_option_id,
        )

    async def has_outstanding_poll(self, attempt: QuizAttempt) -> bool:
        """Whether the attempt's current (first unanswered) question already has
        a sent-but-unanswered poll — used by the race path to no-op."""
        target_qid = self._first_unanswered(attempt)
        if target_qid is None:
            return False
        link = await self._poll_links.get_for_attempt_question(
            attempt.id, uuid.UUID(target_qid)
        )
        return link is not None

    async def next_question_attempt(self, attempt_id: uuid.UUID):
        """Re-fetch an attempt (after an answer) so the next question can be sent."""
        return await self._attempts.get_by_id(attempt_id)

    # ── Answering ─────────────────────────────────────────────────────────

    async def quit_attempt(self, user_id: uuid.UUID) -> bool:
        """Exit the guard's open quiz: abandon ALL IN_PROGRESS attempts.

        Returns True when something was abandoned (False → no open quiz).
        Outstanding polls stay in the chat but their late answers are ignored
        (``record_answer`` drops answers for non-IN_PROGRESS attempts).
        """
        return (await self._attempts.abandon_all_in_progress(user_id)) > 0

    async def record_answer(
        self, telegram_poll_id: str, chosen_shown_position: int
    ) -> AnswerOutcome:
        """Record a PollAnswer and advance/finish the attempt.

        ``chosen_shown_position`` is the index in the shuffled option order the
        guard picked (what Telegram's PollAnswer carries).
        """
        link = await self._poll_links.get(telegram_poll_id)
        if link is None:
            return AnswerOutcome(known=False)  # stale/unknown poll → ignore

        attempt = await self._attempts.get_by_id(link.attempt_id)
        if attempt is None or attempt.status != AttemptStatus.IN_PROGRESS:
            return AnswerOutcome(known=False)  # abandoned/finished → ignore

        qid_key = str(link.question_id)
        if qid_key in attempt.answers:
            # Already recorded (quiz polls are single-answer, but be safe).
            return AnswerOutcome(known=True, already_recorded=True)

        is_correct = chosen_shown_position == link.correct_option_id
        selected_original = link.option_order[chosen_shown_position]
        answers = dict(attempt.answers)
        answers[qid_key] = {"selected": selected_original, "correct": is_correct}

        if len(answers) >= attempt.total_count:
            # Last question answered → score and finalize.
            correct_count = sum(1 for v in answers.values() if v["correct"])
            threshold = await _setting_int(
                self._settings, "procedure_pass_threshold", 80
            )
            total = attempt.total_count
            score_pct = round(correct_count / total * 100) if total else 0
            passed = score_pct >= threshold
            await self._attempts.update(
                attempt.id,
                answers=answers,
                correct_count=correct_count,
                passed=passed,
                finished_at=_now_naive(),
                status=AttemptStatus.FINISHED,
            )
            return AnswerOutcome(
                known=True,
                finished=True,
                correct_count=correct_count,
                total_count=total,
                score_pct=score_pct,
                passed=passed,
                attempt_id=attempt.id,
                procedure_id=attempt.procedure_id,
                threshold=threshold,
            )

        await self._attempts.update(attempt.id, answers=answers)
        return AnswerOutcome(
            known=True,
            finished=False,
            next_question_id=self._first_unanswered_from(attempt.question_ids, answers),
            attempt_id=attempt.id,
            procedure_id=attempt.procedure_id,
        )

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _first_unanswered_from(
        question_ids: list[str], answers: dict
    ) -> str | None:
        for qid in question_ids:
            if qid not in answers:
                return qid
        return None

    def _first_unanswered(self, attempt: QuizAttempt) -> str | None:
        return self._first_unanswered_from(attempt.question_ids, attempt.answers)
