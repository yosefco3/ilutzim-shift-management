"""
Telegram send helpers for the procedure-quiz flow (סד"פ).

Extracted verbatim from ``app.bot.handlers.procedures`` so an HTTP request
context (the WebApp "start quiz" endpoint) can send the first quiz poll without
importing a Router-decorated handlers module. The bot handler still owns the
aiogram event wiring; these helpers own only the sends + the ``QuizPollLink``
recording, and the shared ``start_and_send`` that both the bot callback and the
web endpoint funnel through (so the two start paths cannot drift).
"""

import logging
from dataclasses import dataclass

from app.bot.bot_instance import get_bot
from app.bot.keyboards.procedures import retake_kb
from app.bot.notifications import send_notification

logger = logging.getLogger("ilutzim")


@dataclass
class StartOutcome:
    """Result of ``start_and_send``.

    ``created`` is False when a surviving IN_PROGRESS attempt was reused (the
    double-tap race); ``sent`` is whether a quiz poll was actually delivered.
    """

    created: bool
    sent: bool


async def send_quiz_poll(telegram_id, question) -> str | None:
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


async def send_current_question(telegram_id, attempt, quiz_service) -> bool:
    """Prepare + send the attempt's current question and record its poll link."""
    q = await quiz_service.current_question(attempt)
    if q is None:
        return False
    poll_id = await send_quiz_poll(telegram_id, q)
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


async def send_result(telegram_id, outcome) -> None:
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


async def start_and_send(
    telegram_id, user_id, procedure_id, quiz_service
) -> StartOutcome:
    """Start (or rejoin) an attempt and send its first question.

    Shared by the bot ``on_start_quiz`` callback and the WebApp
    ``POST /procedures/{id}/quiz/start`` endpoint so the two start paths cannot
    drift. ``QuizService.start_attempt`` supersedes any stale IN_PROGRESS
    attempt, which makes a double-start (page + bot, or two taps) safe — exactly
    one active attempt survives, and the first question is (re)sent unless an
    unanswered poll is already outstanding. [EDGE C2]

    Raises ``ValidationException`` (empty bank / not published) or
    ``UserNotFoundException`` (unknown procedure) from ``start_attempt`` — the
    caller decides how to surface them.
    """
    start = await quiz_service.start_attempt(user_id, procedure_id)
    if start.created:
        sent = await send_current_question(telegram_id, start.attempt, quiz_service)
        return StartOutcome(created=True, sent=sent)
    # Race / rejoin: only resend if no poll is already outstanding.
    if await quiz_service.has_outstanding_poll(start.attempt):
        return StartOutcome(created=False, sent=False)
    sent = await send_current_question(telegram_id, start.attempt, quiz_service)
    return StartOutcome(created=False, sent=sent)
