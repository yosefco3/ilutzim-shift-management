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

from app.bot.bot_instance import get_bot
from app.bot.keyboards.procedures import (
    PAGE_SIZE,
    PROC_LIST_PREFIX,
    PROC_MENU_CB,
    PROC_VIEW_PREFIX,
    QUIZ_START_PREFIX,
    procedure_view_kb,
    procedures_list_kb,
    retake_kb,
)
from app.bot.notifications import send_notification, send_procedure
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

    total = len(procedures)
    page = max(0, min(page, (total - 1) // PAGE_SIZE if total else 0))
    window = procedures[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
    items = [(str(p.id), p.title) for p in window]

    if not procedures:
        await callback.message.edit_text("אין נהלים זמינים כרגע.")
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📋 נהלי ביטחון (עמוד {page + 1})",
        reply_markup=procedures_list_kb(items, page=page, total=total),
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

    await send_procedure(
        callback.from_user.id,
        proc.title,
        proc.body_text,
        reply_markup=procedure_view_kb(procedure_id, passed=passed),
    )
    await callback.answer()


# ── Start / retake quiz ─────────────────────────────────────────────────────


@router.callback_query(F.data.startswith(QUIZ_START_PREFIX))
async def on_start_quiz(callback: CallbackQuery, user=None) -> None:
    """Start (or retake) a quiz — both create a fresh sampled attempt."""
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
            start = await quiz_service.start_attempt(user.id, uuid.UUID(procedure_id))
        except ValidationException as exc:
            await callback.answer(exc.message, show_alert=True)
            return

        if start.created:
            await callback.answer("המבחן מתחיל 📝")
            sent = await _send_current_question(
                callback.from_user.id, start.attempt, quiz_service
            )
        else:
            # Race / rejoin: only resend if no poll is already outstanding.
            if await quiz_service.has_outstanding_poll(start.attempt):
                await callback.answer()
            else:
                sent = await _send_current_question(
                    callback.from_user.id, start.attempt, quiz_service
                )
        await session.commit()
    finally:
        await session.close()

    if not sent:
        logger.warning("procedure quiz: could not send a question to tg=%s", callback.from_user.id)


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
            await _send_result(tg_id, outcome)
        else:
            attempt = await quiz_service.next_question_attempt(outcome.attempt_id)
            if attempt is not None:
                await _send_current_question(tg_id, attempt, quiz_service)
        await session.commit()
    finally:
        await session.close()


# ── Send helpers (aiogram sends; state via QuizService) ─────────────────────


async def _send_current_question(telegram_id, attempt, quiz_service) -> bool:
    """Prepare + send the attempt's current question and record its poll link."""
    q = await quiz_service.current_question(attempt)
    if q is None:
        return False
    poll_id = await _send_quiz_poll(telegram_id, q)
    if poll_id is None:
        return False
    await quiz_service.record_poll_link(
        attempt_id=attempt.id,
        question_id=q.question_id,
        telegram_poll_id=poll_id,
        option_order=q.option_order,
        correct_option_id=q.correct_option_id,
    )
    return True


async def _send_quiz_poll(telegram_id, question) -> str | None:
    """Send one non-anonymous quiz poll; returns its Telegram poll id (or None)."""
    try:
        bot = get_bot()
        if bot is None:
            logger.error("send_quiz_poll: bot is None")
            return None
        msg = await bot.send_poll(
            chat_id=telegram_id,
            question=question.text,
            options=question.options,
            type="quiz",
            correct_option_id=question.correct_option_id,
            is_anonymous=False,
        )
        return msg.poll.id if msg.poll else None
    except Exception as exc:
        logger.error("send_quiz_poll: FAILED for tg=%s — %s", telegram_id, exc)
        return None


async def _send_result(telegram_id, outcome) -> None:
    """Pass → success message; fail → score + retake button."""
    if outcome.passed:
        text = (
            "✅ <b>עברת את המבחן!</b>\n\n"
            f"ציון: {outcome.score_pct}% ({outcome.correct_count}/{outcome.total_count})"
        )
        await send_notification(telegram_id, text)
        return

    text = (
        "❌ <b>לא עברת את המבחן</b>\n\n"
        f"ציון: {outcome.score_pct}% ({outcome.correct_count}/{outcome.total_count})\n"
        f"יש להגיע לפחות ל-{outcome.threshold}% כדי לעבור.\n\n"
        "רוצה לנסות שוב?"
    )
    await send_notification(
        telegram_id, text, reply_markup=retake_kb(outcome.procedure_id)
    )


async def _callback_user(callback: CallbackQuery):
    """Fallback user resolution when the middleware did not inject one."""
    session = await _session()
    try:
        return await _resolve_user(session, callback.from_user.id)
    finally:
        await session.close()
