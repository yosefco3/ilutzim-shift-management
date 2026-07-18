"""
Procedure-quiz bot handlers (סד"פ).

Guard-facing flow, registered (under ``PROCEDURES_ENABLED``) BEFORE the core
router so the menu/quiz callbacks are not swallowed by core's catch-all:
  - "נהלים" menu entry → paginated list of PUBLISHED procedures → view one
    (re-sends the text + a start-quiz button; ✅ if the guard already passed).
  - Start / retake → ``QuizService`` opens an attempt, sends question 1 as a
    non-anonymous quiz poll.
  - ``PollAnswer`` → resolve the user ourselves (``AuthMiddleware`` only covers
    message/callback_query), reject inactive guards, record the answer, send the
    next poll or score the attempt (pass ≥ 80% / fail + retake button).

The aiogram sends live here; all state lives in ``QuizService`` (pure DB logic),
which makes the whole flow testable with an in-memory session + a mocked bot.
"""

import logging
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, PollAnswer

from app.bot.keyboards.procedures import (
    PAGE_SIZE,
    PROC_LIST_PREFIX,
    PROC_MENU_CB,
    PROC_VIEW_PREFIX,
    QUIZ_QUIT_CB,
    QUIZ_START_PREFIX,
    order_and_mark_procedures,
    procedure_view_kb,
    procedures_list_kb,
)
from app.bot.notifications import send_procedure_card
from app.bot.quiz_sender import send_current_question, send_result, start_and_send
from app.exceptions import ValidationException

logger = logging.getLogger("ilutzim")

router = Router()


# ── Session helper ──────────────────────────────────────────────────────────


async def _session():
    """Open a fresh DB session for a bot handler (caller commits/closes)."""
    from app.database import get_session

    ctx = get_session()
    return await ctx.__aenter__()


async def _resolve_user(session, telegram_id: int):
    """PollAnswer has no AuthMiddleware — resolve + active-check the guard here."""
    from app.repositories.user_repository import UserRepository
    from app.services.user_service import UserService

    user = await UserService(UserRepository(session)).get_by_telegram_id(str(telegram_id))
    if user is None or not user.is_active:
        return None
    return user


# ── Menu / list / view ──────────────────────────────────────────────────────


@router.callback_query(F.data == PROC_MENU_CB)
async def on_menu(callback: CallbackQuery) -> None:
    await _show_list(callback, page=0)


@router.callback_query(F.data.startswith(PROC_LIST_PREFIX))
async def on_list_page(callback: CallbackQuery) -> None:
    page = int(callback.data.removeprefix(PROC_LIST_PREFIX) or "0")
    await _show_list(callback, page=page)


async def _show_list(callback: CallbackQuery, *, page: int) -> None:
    from app.procedures.repositories.attempt_repository import QuizAttemptRepository
    from app.procedures.repositories.procedure_repository import ProcedureRepository

    session = await _session()
    try:
        repo = ProcedureRepository(session)
        procedures = await repo.list_published()
    finally:
        await session.close()

    if not procedures:
        await callback.message.edit_text("אין נהלים זמינים כרגע.")
        await callback.answer()
        return

    # Default procedure leads with a ⭐ marker; the rest stay newest-first.
    items = order_and_mark_procedures(procedures)
    total = len(items)
    page = max(0, min(page, (total - 1) // PAGE_SIZE if total else 0))
    window = items[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]

    await callback.message.edit_text(
        f"📋 נהלי ביטחון (עמוד {page + 1})",
        reply_markup=procedures_list_kb(window, page=page, total=total),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(PROC_VIEW_PREFIX))
async def on_view(callback: CallbackQuery) -> None:
    from app.procedures.repositories.attempt_repository import QuizAttemptRepository
    from app.procedures.repositories.procedure_repository import ProcedureRepository

    procedure_id = callback.data.removeprefix(PROC_VIEW_PREFIX)
    session = await _session()
    try:
        repo = ProcedureRepository(session)
        proc = await repo.get_by_id(uuid.UUID(procedure_id))
        if proc is None:
            await callback.answer("הנוהל לא נמצא.", show_alert=True)
            return
        passed = False
        user = await _resolve_user(session, callback.from_user.id)
        if user is not None:
            passed = await QuizAttemptRepository(session).has_passed(user.id, proc.id)
    finally:
        await session.close()

    await send_procedure_card(
        callback.from_user.id,
        proc.title,
        reply_markup=procedure_view_kb(procedure_id, passed=passed),
    )
    await callback.answer()


# ── Start / retake quiz ─────────────────────────────────────────────────────


@router.callback_query(F.data.startswith(QUIZ_START_PREFIX))
async def on_start_quiz(callback: CallbackQuery, user=None) -> None:
    """Start (or retake) a quiz — both create a fresh sampled attempt.

    Reroutes through the shared ``start_and_send`` (same path the WebApp
    "start quiz" endpoint uses) so bot and web starts cannot drift.
    """
    if user is None:
        # AuthMiddleware provides `user` for callback_query; defend anyway.
        user = await _callback_user(callback)
    if user is None:
        await callback.answer("משתמש לא זמין. שלח /start.", show_alert=True)
        return

    procedure_id = callback.data.removeprefix(QUIZ_START_PREFIX)
    from app.procedures.dependencies import build_quiz_service

    session = await _session()
    sent = False
    try:
        quiz_service = build_quiz_service(session)
        try:
            outcome = await start_and_send(
                callback.from_user.id, user.id, uuid.UUID(procedure_id), quiz_service
            )
        except ValidationException as exc:
            await callback.answer(exc.message, show_alert=True)
            return

        # Preserve the original callback-answer UX:
        # - created attempt → "המבחן מתחיל"
        # - reused attempt with an outstanding poll → silent ack
        # - reused attempt, poll resent → no special message
        if outcome.created:
            await callback.answer("המבחן מתחיל 📝")
        elif not outcome.sent:
            await callback.answer()
        sent = outcome.sent
        await session.commit()
    finally:
        await session.close()

    if not sent:
        logger.warning("procedure quiz: could not send a question to tg=%s", callback.from_user.id)


# ── Quit quiz (the 🚪 button on every quiz poll) ────────────────────────────


@router.callback_query(F.data == QUIZ_QUIT_CB)
async def on_quiz_quit(callback: CallbackQuery, user=None) -> None:
    """Exit the open quiz: abandon the guard's IN_PROGRESS attempt(s).

    Idempotent — tapping the button on an old poll after the quiz already
    ended/quit just answers "אין מבחן פתוח". Late answers to the now-abandoned
    polls are ignored by ``record_answer``.
    """
    from app.procedures.repositories.attempt_repository import QuizAttemptRepository

    if user is None:
        user = await _callback_user(callback)
    if user is None:
        await callback.answer("משתמש לא זמין. שלח /start.", show_alert=True)
        return

    session = await _session()
    try:
        quit_count = await QuizAttemptRepository(session).abandon_all_in_progress(user.id)
        await session.commit()
    finally:
        await session.close()

    if quit_count == 0:
        await callback.answer("אין מבחן פתוח")
        return
    await callback.answer("יצאת מהמבחן")
    await callback.message.answer(
        "🚪 יצאת מהמבחן. אפשר להתחיל אותו מחדש מתי שתרצה — מהכפתור בהודעת הנוהל."
    )


# ── Poll answer (quiz advance + scoring) ────────────────────────────────────


@router.poll_answer()
async def on_poll_answer(poll_answer: PollAnswer) -> None:
    """Record an answer; send the next poll or score the attempt.

    AuthMiddleware does not cover ``poll_answer``, so the user is resolved here
    and inactive guards are rejected.
    """
    tg_id = poll_answer.user.id if poll_answer.user else None
    if tg_id is None:
        return
    if not poll_answer.option_ids:
        return
    chosen = poll_answer.option_ids[0]

    from app.procedures.dependencies import build_quiz_service

    session = await _session()
    try:
        user = await _resolve_user(session, tg_id)
        if user is None:
            return  # unknown or deactivated guard — ignore

        quiz_service = build_quiz_service(session)
        outcome = await quiz_service.record_answer(poll_answer.poll_id, chosen)
        if not outcome.known or outcome.already_recorded:
            return  # stale/unknown poll or duplicate → ignore silently

        if outcome.finished:
            await send_result(tg_id, outcome)
        else:
            attempt = await quiz_service.next_question_attempt(outcome.attempt_id)
            if attempt is not None:
                await send_current_question(tg_id, attempt, quiz_service)
        await session.commit()
    finally:
        await session.close()


# ── Send helpers ─────────────────────────────────────────────────────────────
#
# The quiz-poll / result senders live in ``app.bot.quiz_sender`` (extracted so
# the WebApp "start quiz" HTTP endpoint can share them). ``send_current_question``,
# ``send_result`` and ``start_and_send`` are imported at the top of this module.


async def _callback_user(callback: CallbackQuery):
    """Fallback user resolution when the middleware did not inject one."""
    session = await _session()
    try:
        return await _resolve_user(session, callback.from_user.id)
    finally:
        await session.close()
