"""
The composed persistent bottom keyboard (reply keyboard) for guards.

Two possible rows, each independently present:
- "📝 הגשת/עריכת אילוצים" — a ``web_app`` button straight to the ``/submit``
  form. Shown ONLY while a week is OPEN, so the keyboard mirrors whether
  submitting is currently possible.
- The attendance punch row (🟢/🔴) — shown while ``ATTENDANCE_ENABLED``.

Telegram can only swap a reply keyboard by sending a message, so every bot
reply re-attaches the freshly-composed keyboard (see the attendance handlers
and /start), and the week-opened/locked broadcasts carry it too. After the
SILENT Sunday rollover the submit button lingers until the guard's next
interaction — accepted: a stale tap opens the form, which shows
"אין שבוע פתוח כרגע" (see features-prompts/submit_reply_keyboard/EDGE_CASES).
"""

import logging

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from app.bot.keyboards.attendance import BTN_PUNCH_IN, BTN_PUNCH_OUT

logger = logging.getLogger("ilutzim")

BTN_SUBMIT_CONSTRAINTS = "📝 הגשת/עריכת אילוצים"


def compose_reply_kb(
    *, week_open: bool, attendance_enabled: bool
) -> ReplyKeyboardMarkup | None:
    """Build the composed keyboard for the given state; None when it has no rows.

    The submit row leads (the time-sensitive action), the punch row follows.
    Callers that get None should leave the existing keyboard untouched — except
    the week-locked broadcast, which sends ``ReplyKeyboardRemove`` instead so a
    now-dead submit button doesn't linger (attendance-off deployments).
    """
    rows: list[list[KeyboardButton]] = []
    if week_open:
        # Lazy import (matching the other bot keyboards) so the current settings
        # object is read at call time.
        from app.bot.webapp import submit_webapp_url

        rows.append([
            KeyboardButton(
                text=BTN_SUBMIT_CONSTRAINTS,
                web_app=WebAppInfo(url=submit_webapp_url()),
            )
        ])
    if attendance_enabled:
        rows.append(
            [KeyboardButton(text=BTN_PUNCH_IN), KeyboardButton(text=BTN_PUNCH_OUT)]
        )
    if not rows:
        return None
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=(
            "החתמת נוכחות" if attendance_enabled and not week_open else "פעולות מהירות"
        ),
    )


async def main_reply_kb() -> ReplyKeyboardMarkup | None:
    """Compose the keyboard from the CURRENT state (own short session).

    Never raises: a DB failure falls back to the punch-only keyboard (keyboard
    freshness is never worth failing a punch reply over). Opens its own session
    so the many attendance call sites need zero session plumbing — the OPEN-week
    lookup is a limit-1 query on an indexed status column.
    """
    from app.config import get_settings

    attendance = get_settings().ATTENDANCE_ENABLED
    week_open = False
    try:
        from app.database import get_session
        from app.repositories.schedule_week_repository import ScheduleWeekRepository

        async with get_session() as session:
            week_open = (
                await ScheduleWeekRepository(session).get_current_open_week()
            ) is not None
    except Exception as exc:  # noqa: BLE001 — degrade, never break the reply
        logger.warning("main_reply_kb: open-week lookup failed — %s", exc)
    return compose_reply_kb(week_open=week_open, attendance_enabled=attendance)
