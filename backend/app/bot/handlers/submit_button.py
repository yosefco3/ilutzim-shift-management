"""
Handler for the bottom-keyboard "📝 הגשת/עריכת אילוצים" TEXT button.

Why a text button answered here, and not a ``web_app`` KeyboardButton opening
the form directly: Telegram does NOT pass ``initData`` to Mini Apps launched
from a reply-keyboard button (Bot API: WebAppInitData "is empty if the Mini App
was launched from a keyboard button"). Without initData the form cannot
authenticate — in production the submit POST fails with 401, and in dev the
``__DEV_MODE__`` bypass silently authenticates as an arbitrary user. The INLINE
web_app button this handler answers with does carry signed initData, so each
guard is identified by their own telegram_id (same rule as core._show_main_menu).

Included by ``bot_router`` unconditionally, BEFORE ``main_router`` (whose
catch-all "לא הבנתי" would otherwise swallow the button text).
"""

import logging

from aiogram import F, Router
from aiogram.types import Message, ReplyKeyboardRemove

from app.bot.keyboards.reply_kb import BTN_SUBMIT_CONSTRAINTS, main_reply_kb

logger = logging.getLogger("ilutzim")


def build_router() -> Router:
    """Return a FRESH router for the submit button.

    A factory (not a module-level router) because this router is included
    unconditionally: a module-level Router would already be attached to the
    previous Dispatcher whenever the dispatcher singleton is rebuilt, and
    aiogram refuses to re-attach it.
    """
    router = Router()
    router.message(F.text == BTN_SUBMIT_CONSTRAINTS)(on_submit_button)
    return router


async def on_submit_button(message: Message) -> None:
    """Answer the bottom submit button with the inline submit (web_app) button.

    Stale-button case (the keyboard lingers after the silent Sunday rollover):
    when no week is OPEN, say so and re-attach the freshly-composed keyboard so
    the dead submit button goes away.
    """
    week_open = False
    try:
        from app.database import get_session
        from app.repositories.schedule_week_repository import ScheduleWeekRepository

        async with get_session() as session:
            week_open = (
                await ScheduleWeekRepository(session).get_current_open_week()
            ) is not None
    except Exception:  # noqa: BLE001 — reply something rather than go silent
        logger.exception("submit_button: open-week lookup failed")
        await message.answer("משהו השתבש 😕 נסה שוב בעוד רגע.")
        return

    if not week_open:
        kb = await main_reply_kb()
        await message.answer(
            "אין שבוע פתוח להגשה כרגע.",
            reply_markup=kb if kb is not None else ReplyKeyboardRemove(),
        )
        return

    # Lazy import (matching the other bot keyboards) so the current settings
    # object is read at call time.
    from app.bot.keyboards.inline_kb import submit_constraints_kb

    await message.answer(
        "להגשה או עריכה של האילוצים — לחצו על הכפתור 👇",
        reply_markup=submit_constraints_kb(),
    )
