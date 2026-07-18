"""
Proactive notification helpers for the Telegram bot.
"""

import html
import logging
from datetime import date, timedelta
from itertools import groupby

from app.bot.bot_instance import get_bot

logger = logging.getLogger("ilutzim")

# Hebrew weekday names, Sunday=0 … Saturday=6 (matches day_index everywhere).
_HE_DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]


async def send_notification(telegram_id: int, text: str, reply_markup=None) -> bool:
    """Send a message to a single Telegram user."""
    try:
        bot = get_bot()
        if bot is None:
            logger.error("send_notification: bot is None — cannot send to telegram_id=%s", telegram_id)
            return False
        logger.info("send_notification: sending to telegram_id=%s (text length=%d)", telegram_id, len(text))
        await bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)
        logger.info("send_notification: SUCCESS for telegram_id=%s", telegram_id)
        return True
    except Exception as exc:
        logger.error("send_notification: FAILED for telegram_id=%s — %s", telegram_id, exc, exc_info=True)
        return False


async def broadcast_notifications(telegram_ids: list[int], text: str, reply_markup=None) -> int:
    """Send the same message to multiple users. Returns success count."""
    success = 0
    for tg_id in telegram_ids:
        if await send_notification(tg_id, text, reply_markup=reply_markup):
            success += 1
    return success


async def notify_week_opened(week_start: date, week_end: date, telegram_ids: list[int]):
    """Notify users that a new week is open for submissions.

    Uses DD/MM/YYYY date format and includes the webapp URL.
    Returns count of successfully notified guards.
    """
    from app.bot.keyboards.inline_kb import submit_constraints_kb

    start_fmt = week_start.strftime("%d/%m/%Y")
    end_fmt = week_end.strftime("%d/%m/%Y")

    text = (
        "🔔 שבוע חדש נפתח להגשה!\n\n"
        f"תאריכים: {start_fmt} - {end_fmt}"
    )
    count = await broadcast_notifications(
        telegram_ids, text, reply_markup=submit_constraints_kb()
    )
    logger.info("Week-opened notification sent to %d/%d users", count, len(telegram_ids))
    return count


async def notify_guard_welcome(telegram_id: int, first_name: str, last_name: str) -> bool:
    """Send a welcome message to a newly added guard."""
    full_name = f"{first_name} {last_name}".strip()
    logger.info(
        "notify_guard_welcome: telegram_id=%s, name=%s",
        telegram_id, full_name,
    )
    text = (
        f"👋 שלום {full_name}!\n\n"
        f"נרשמת בהצלחה למערכת ניהול האילוצים.\n"
        f"מעתה תקבל הודעות ותזכורות דרך הבוט הזה."
    )
    return await send_notification(telegram_id, text)


async def notify_week_locked(week_start: date, week_end: date, telegram_ids: list[int]):
    """Notify users that a week was finalized (LOCKED) — no more edits.

    Fires only on a manual ``change_week_status(LOCKED, notify=True)``. The normal
    path to LOCKED is the Sunday rollover, which locks silently (notify=False), and
    "publish" no longer locks at all — so in practice this broadcast is rarely used.
    """
    start_fmt = week_start.strftime("%d/%m/%Y")
    end_fmt = week_end.strftime("%d/%m/%Y")
    text = f"🔒 שבוע {start_fmt} - {end_fmt} ננעל — לא ניתן עוד לעדכן אילוצים"
    count = await broadcast_notifications(telegram_ids, text)
    logger.info("Week-locked notification sent to %d/%d users", count, len(telegram_ids))
    return count


async def notify_week_closed(week_start: date, week_end: date, telegram_ids: list[int]):
    """Notify guards that the submission window was auto-locked (OPEN → CLOSED).

    This is the broadcast for the scheduled auto-lock TIME (the counterpart to
    ``notify_week_opened``). The week is no longer open for submissions; guards
    who have a problem are directed to the unit manager.
    Returns count of successfully notified guards.
    """
    start_fmt = week_start.strftime("%d/%m/%Y")
    end_fmt = week_end.strftime("%d/%m/%Y")
    text = (
        "🔒 השבוע ננעל להגשה.\n\n"
        f"תאריכים: {start_fmt} - {end_fmt}\n\n"
        "לא ניתן עוד להגיש או לעדכן אילוצים.\n"
        "אם יש בעיה, אנא פנה לאחראי היחידה."
    )
    count = await broadcast_notifications(telegram_ids, text)
    logger.info("Week-closed notification sent to %d/%d users", count, len(telegram_ids))
    return count


async def notify_closing_reminder(
    week_start: date,
    deadline_text: str,
    recipients: list[dict],
    week_end: date | None = None,
):
    """Remind guards who haven't submitted yet to submit before the deadline.

    ``recipients`` is a list of ``{"telegram_id": int, "name": str}`` dicts so the
    message can greet each registered guard by name. The message includes a WebApp
    button to submit directly — registered guards never need to send ``/start``.
    Returns count of successfully notified guards.
    """
    from app.bot.keyboards.inline_kb import submit_constraints_kb

    start_fmt = week_start.strftime("%d/%m/%Y")
    week_range = start_fmt
    if week_end is not None:
        week_range = f"{start_fmt} - {week_end.strftime('%d/%m/%Y')}"

    keyboard = submit_constraints_kb()
    count = 0
    for recipient in recipients:
        name = (recipient.get("name") or "").strip()
        greeting = f"שלום {name}! 👋\n\n" if name else ""
        text = (
            f"⏰ <b>תזכורת!</b>\n\n"
            f"{greeting}"
            f"טרם הגשת את האילוצים לשבוע {week_range}.\n"
            f"ההגשה תיסגר {deadline_text}.\n\n"
            f"אנא הגש עכשיו דרך הכפתור למטה 👇"
        )
        if await send_notification(recipient["telegram_id"], text, reply_markup=keyboard):
            count += 1
    logger.info("Closing reminder sent to %d/%d users", count, len(recipients))
    return count


async def notify_admin_filled_constraints(telegram_id: int, week_label: str) -> bool:
    """Notify a guard that an admin filled their constraints on their behalf."""
    from app.bot.keyboards.inline_kb import submission_success_kb

    text = (
        "📝 האדמין מילא עבורך את האילוצים\n\n"
        f"שבוע: {week_label}\n\n"
        "ניתן לצפות ולערוך את האילוצים כל עוד השבוע פתוח."
    )
    try:
        bot = get_bot()
        if bot is None:
            logger.error("notify_admin_filled_constraints: bot is None")
            return False
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=submission_success_kb(),
        )
        logger.info("Admin-filled-constraints notification sent to telegram_id=%s", telegram_id)
        return True
    except Exception as exc:
        logger.error("notify_admin_filled_constraints: FAILED for telegram_id=%s — %s", telegram_id, exc)
        return False


async def notify_submission_success(telegram_id: int, week_label: str) -> bool:
    """Notify a guard that their submission was received successfully."""
    from app.bot.keyboards.inline_kb import submission_success_kb

    text = (
        "✅ האילוצים נשלחו בהצלחה!\n\n"
        f"שבוע: {week_label}\n\n"
        "ניתן לערוך את האילוצים כל עוד השבוע פתוח."
    )
    try:
        bot = get_bot()
        if bot is None:
            logger.error("notify_submission_success: bot is None")
            return False
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=submission_success_kb(),
        )
        logger.info("Submission success notification sent to telegram_id=%s", telegram_id)
        return True
    except Exception as exc:
        logger.error("notify_submission_success: FAILED for telegram_id=%s — %s", telegram_id, exc)
        return False


def format_personal_schedule(guard_schedule, week_start: date, week_end: date) -> str:
    """Render one guard's weekly schedule as a Hebrew Telegram message.

    ``guard_schedule`` is a ``GuardSchedule`` from the schedule read model (task
    01); its shifts arrive already merged and sorted by ``(day_index, start)``, so
    this only groups by day and prints — it does not merge or reorder. Only days
    with shifts are shown. A cross-midnight shift (``end <= start``) is tagged
    "(עד למחרת)". A guard with no shifts gets a short "not scheduled" line.

    **Event** shifts (non-splitting positions — רענון, ישיבת מועצה) are pulled out
    of the day-by-day bullet list and printed as dedicated 📣 sentences after it,
    so they stand out from the routine schedule.
    """
    start_fmt = week_start.strftime("%d/%m/%Y")
    end_fmt = week_end.strftime("%d/%m/%Y")

    if not guard_schedule.shifts:
        return (
            f"לא שובצת השבוע ({week_start.strftime('%d/%m')}–"
            f"{week_end.strftime('%d/%m')}). לשאלות פנה לאחראי היחידה."
        )

    normal = [s for s in guard_schedule.shifts if not s.is_event]
    events = [s for s in guard_schedule.shifts if s.is_event]

    lines = [f"🗓️ הסידור שלך לשבוע {start_fmt} – {end_fmt}", ""]
    for day_index, group in groupby(normal, key=lambda s: s.day_index):
        day_date = (week_start + timedelta(days=day_index)).strftime("%d/%m")
        lines.append(f"{_HE_DAYS[day_index]} {day_date}")
        for sh in group:
            overnight = " (עד למחרת)" if sh.end <= sh.start else ""
            lines.append(f"  • {sh.position_name} · {sh.start}–{sh.end}{overnight}")

    # 📣 Event sentences — e.g. "יש לך רענון ביום ראשון 12/07 / משעה 07:00 עד 15:00".
    if events:
        if lines[-1] != "":
            lines.append("")
        for sh in events:
            day_date = (week_start + timedelta(days=sh.day_index)).strftime("%d/%m")
            overnight = " (עד למחרת)" if sh.end <= sh.start else ""
            lines.append(
                f"📣 יש לך {sh.position_name} ביום {_HE_DAYS[sh.day_index]} {day_date}"
            )
            lines.append(f"   משעה {sh.start} עד {sh.end}{overnight}")

    lines += ["", "בהצלחה! לשאלות פנה לאחראי היחידה"]
    return "\n".join(lines)


async def notify_personal_schedule(telegram_id, text: str) -> bool:
    """Send one guard their personal-schedule message (thin wrapper for a
    dedicated log line; delegates delivery to ``send_notification``)."""
    logger.info("notify_personal_schedule: sending to telegram_id=%s", telegram_id)
    return await send_notification(telegram_id, text)


async def send_document(
    telegram_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str | None = None,
) -> bool:
    """Send a document (e.g. the general schedule Excel) to a single Telegram
    user. Mirrors ``send_notification``: never raises, returns success/failure."""
    try:
        bot = get_bot()
        if bot is None:
            logger.error(
                "send_document: bot is None — cannot send to telegram_id=%s",
                telegram_id,
            )
            return False
        # Imported lazily so importing this module stays bot-library-light.
        from aiogram.types import BufferedInputFile

        document = BufferedInputFile(file_bytes, filename=filename)
        logger.info(
            "send_document: sending '%s' (%d bytes) to telegram_id=%s",
            filename, len(file_bytes), telegram_id,
        )
        await bot.send_document(
            chat_id=telegram_id, document=document, caption=caption
        )
        logger.info("send_document: SUCCESS for telegram_id=%s", telegram_id)
        return True
    except Exception as exc:
        logger.error(
            "send_document: FAILED for telegram_id=%s — %s",
            telegram_id, exc, exc_info=True,
        )
        return False


async def send_photo(
    telegram_id: int,
    image_bytes: bytes,
    filename: str,
    caption: str | None = None,
) -> bool:
    """Send an image (the general schedule PNG) to a single Telegram user as a
    photo — it previews inline and opens with one tap, far friendlier on a phone
    than a document. Mirrors ``send_document``: never raises, returns success."""
    try:
        bot = get_bot()
        if bot is None:
            logger.error(
                "send_photo: bot is None — cannot send to telegram_id=%s",
                telegram_id,
            )
            return False
        # Imported lazily so importing this module stays bot-library-light.
        from aiogram.types import BufferedInputFile

        photo = BufferedInputFile(image_bytes, filename=filename)
        logger.info(
            "send_photo: sending '%s' (%d bytes) to telegram_id=%s",
            filename, len(image_bytes), telegram_id,
        )
        await bot.send_photo(chat_id=telegram_id, photo=photo, caption=caption)
        logger.info("send_photo: SUCCESS for telegram_id=%s", telegram_id)
        return True
    except Exception as exc:
        logger.error(
            "send_photo: FAILED for telegram_id=%s — %s",
            telegram_id, exc, exc_info=True,
        )
        return False


# ── Procedure card (the short WebApp-pointer message) ────────────────────────


async def send_procedure_card(
    telegram_id, title: str, reply_markup=None
) -> bool:
    """Send ONE short procedure card to a guard: the bold title + a one-line
    prompt, with the read (web_app) + start-quiz buttons as ``reply_markup``.

    The full procedure body lives in the WebApp reading page now — this card is
    intentionally tiny (no chunking). Same never-raise/bool contract as
    ``send_notification`` (a blocked bot logs and counts as a skipped send).
    """
    try:
        bot = get_bot()
        if bot is None:
            logger.error(
                "send_procedure_card: bot is None — cannot send to telegram_id=%s",
                telegram_id,
            )
            return False
        text = (
            f"📜 <b>{html.escape(title)}</b>\n\n"
            "לחצו על ״📖 קרא נוהל״ לקריאת הנוהל המלא, ולאחר מכן ״▶️ התחל מבחן״."
        )
        await bot.send_message(
            chat_id=telegram_id, text=text, reply_markup=reply_markup
        )
        logger.info("send_procedure_card: SUCCESS for telegram_id=%s", telegram_id)
        return True
    except Exception as exc:
        logger.error(
            "send_procedure_card: FAILED for telegram_id=%s — %s",
            telegram_id, exc, exc_info=True,
        )
        return False
