"""
Core Telegram bot handler – aiogram v3 dispatcher with all handlers.
"""

import logging
import re
from contextlib import asynccontextmanager
from datetime import date

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.bot.keyboards.inline_kb import (
    DAY_NAMES,
    availability_kb,
    main_menu_kb,
    weekday_kb,
)
from app.config import settings
from app.constants import WeekStatus

logger = logging.getLogger("ilutzim")
router = Router()


# ─── FSM States ────────────────────────────────────────────

class SubmissionFlow(StatesGroup):
    selecting_days = State()


class PhoneVerification(StatesGroup):
    waiting_for_phone = State()


# ─── Dependency helpers ────────────────────────────────────

async def _get_services():
    """Create services with a dedicated async DB session for bot handlers.

    Returns (user_svc, week_svc, sub_svc, session) tuple.
    Each call creates a fresh session.  Caller is responsible for committing
    the session (e.g. ``await session.commit()``) when writes are performed.
    """
    from app.services.user_service import UserService
    from app.services.submission_service import SubmissionService
    from app.services.week_service import WeekService
    from app.database import get_session
    from app.repositories.user_repository import UserRepository
    from app.repositories.submission_repository import SubmissionRepository
    from app.repositories.schedule_week_repository import ScheduleWeekRepository

    session_ctx = get_session()
    session = await session_ctx.__aenter__()
    logger.info("Bot _get_services: opened DB session %s", id(session))

    user_repo = UserRepository(session)
    sub_repo = SubmissionRepository(session)
    week_repo = ScheduleWeekRepository(session)

    user_svc = UserService(user_repo)
    week_svc = WeekService(week_repo, user_repo)
    sub_svc = SubmissionService(sub_repo, user_repo, week_repo)
    return user_svc, week_svc, sub_svc, session


# ─── /start ────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start – verify user, register if new, show main menu."""
    await state.clear()
    telegram_id = message.from_user.id
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""

    user_svc, _, _, session = await _get_services()

    # Check if this Telegram ID is already linked to a user
    user = await user_svc.get_by_telegram_id(telegram_id)

    if user is not None:
        # Already registered — show the menu.
        #
        # We intentionally do NOT sync the name from the Telegram profile here.
        # The authoritative name is the one the admin entered when creating the
        # user (often Hebrew); the guard's Telegram profile name (often English)
        # must never overwrite it. Syncing on every /start used to clobber the
        # admin-entered Hebrew name with the English Telegram name.
        # Greet with the stored (admin-entered) name, not the Telegram profile name.
        greeting_name = user.first_name or first_name
        try:
            await _show_main_menu(message, greeting_name)
        except Exception as exc:
            logger.error("Failed to show main menu: %s", exc, exc_info=True)
            await message.answer(f"שלום {greeting_name}! 👋\nברוך הבא למערכת ניהול האילוצים.\nשלח /start לתפריט.")
    else:
        # Not yet linked — ask for phone number to verify identity
        await state.set_state(PhoneVerification.waiting_for_phone)
        await message.answer(
            "👋 שלום!\n\n"
            "כדי להשתמש במערכת, עליך לאמת את מספר הטלפון שלך.\n"
            "נא לשלוח את מספר הטלפון שאיתו נרשמת למערכת\n"
            "(ללא מקף, ללא רווחים).\n\n"
            "לדוגמה: 0501234567"
        )


# ─── Phone verification ────────────────────────────────────

@router.message(PhoneVerification.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Process phone number and link Telegram ID to user."""
    await state.clear()
    phone_raw = message.text.strip()
    telegram_id = message.from_user.id
    logger.info("Phone verification: raw input=%r, telegram_id=%s", phone_raw, telegram_id)

    # Normalize to 972XXXXXXXXX format (same format stored in DB)
    phone = phone_raw.replace("-", "").replace(" ", "")
    if phone.startswith("+"):
        phone = phone[1:]

    # Local format 05XXXXXXXX → 972XXXXXXXXX
    if phone.startswith("05") and len(phone) == 10 and phone.isdigit():
        phone = "972" + phone[1:]
    # Already has 972 prefix
    elif phone.startswith("972") and len(phone) == 12 and phone.isdigit():
        pass  # already in correct format
    else:
        logger.warning("Phone verification: invalid format — %r", phone_raw)
        await message.answer(
            "❌ מספר הטלפון אינו תקין.\n"
            "נא לשלוח מספר טלפון ישראלי בן 10 ספרות המתחיל ב-05\n"
            "(ללא מקף, ללא רווחים).\n\n"
            "לדוגמה: 0501234567"
        )
        await state.set_state(PhoneVerification.waiting_for_phone)
        return

    user_svc, _, _, session = await _get_services()

    # Find user by phone
    logger.info("Phone verification: looking up phone=%s for telegram_id=%s", phone, telegram_id)
    user = await user_svc.get_user_by_phone(phone)
    if user is None:
        logger.warning("Phone verification FAILED — phone=%s not found in DB (telegram_id=%s)", phone, telegram_id)
        await message.answer(
            "❌ מספר הטלפון לא נמצא במערכת.\n"
            "נא לוודא שהמספר תואם למספר שנרשמת איתו.\n\n"
            "נסה שוב או פנה למנהל המערכת."
        )
        await state.set_state(PhoneVerification.waiting_for_phone)
        return

    if not user.is_active:
        await message.answer(
            "❌ המשתמש שלך אינו פעיל במערכת.\n"
            "פנה למנהל המערכת לפרטים."
        )
        return

    # Link telegram_id to the user
    try:
        await user_svc.link_telegram(phone, str(telegram_id))
        await session.commit()
        logger.info(
            "Phone verification SUCCESS: user_id=%s, phone=%s, telegram_id=%s linked",
            user.id, phone, telegram_id,
        )
    except Exception as exc:
        logger.error("Failed to link telegram: phone=%s, telegram_id=%s — %s", phone, telegram_id, exc, exc_info=True)
        await message.answer(
            "❌ שגיאה בחיבור החשבון. נסה שוב מאוחר יותר."
        )
        return

    # Success — send welcome notification via the shared helper
    display_name = user.first_name or message.from_user.first_name or "מאבטח"
    try:
        from app.bot.notifications import notify_guard_welcome
        await notify_guard_welcome(
            telegram_id,
            user.first_name or "",
            user.last_name or "",
        )
    except Exception as notif_exc:
        logger.warning("Could not send welcome notification: %s", notif_exc)
        # Fallback — still show a success message in the chat
        await message.answer(
            f"✅ {display_name}, החשבון חובר בהצלחה!\n\n"
            f"מעתה תקבל הודעות ותזכורות דרך הבוט."
        )
    try:
        await _show_main_menu(message, display_name)
    except Exception as exc:
        logger.error("Failed to show main menu after phone verification: %s", exc, exc_info=True)


async def _show_main_menu(message: Message, display_name: str):
    """Show the main menu to an authenticated user.

    Logic:
    - If a week is OPEN → check if user already submitted.
      - Submitted → button "עריכת אילוצים" → webapp
      - Not submitted → button "הגשת אילוצים" → webapp
    - If latest week is LOCKED → "השבוע נעול — ההגשה נסגרה" (no buttons)
    - If latest week is CLOSED → "ההגשה סגורה כרגע" (no buttons)
    """
    from app.database import get_session
    from app.repositories.user_repository import UserRepository
    from app.repositories.submission_repository import SubmissionRepository
    from app.repositories.schedule_week_repository import ScheduleWeekRepository
    from app.services.user_service import UserService
    from app.services.submission_service import SubmissionService
    from app.services.week_service import WeekService
    from app.bot.webapp import submit_webapp_url

    telegram_id = message.from_user.id
    webapp_url = submit_webapp_url(tg_id=telegram_id)

    # Private URL detection
    private_pattern = r"(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)"
    is_private = bool(re.search(private_pattern, webapp_url))

    # Open a short-lived DB session to query week + submission status
    session_ctx = get_session()
    session = await session_ctx.__aenter__()
    try:
        user_repo = UserRepository(session)
        week_repo = ScheduleWeekRepository(session)
        sub_repo = SubmissionRepository(session)

        week_svc = WeekService(week_repo, user_repo)
        sub_svc = SubmissionService(sub_repo, user_repo, week_repo)
        user_svc = UserService(user_repo)

        # 1) Check if there's an OPEN week
        open_week = await week_svc.get_current_open_week()

        if open_week is not None:
            # Week is open — check if user already submitted
            user = await user_svc.get_by_telegram_id(telegram_id)
            already_submitted = False
            if user is not None:
                existing = await sub_svc.get_submission(user.id, open_week.id)
                already_submitted = existing is not None

            button_text = "✏️ עריכת אילוצים" if already_submitted else "📅 הגשת אילוצים"
            text = f"שלום {display_name}! 👋\nברוך הבא למערכת ניהול האילוצים."

            if not is_private and webapp_url.startswith("https://"):
                # MUST be a real Telegram WebApp button (web_app=), NOT a plain
                # url= button. A url= button opens an ordinary browser tab with no
                # Telegram context, so window.Telegram.WebApp.initData is empty and
                # the frontend falls back to the __DEV_MODE__ auth sentinel — which
                # authenticates every guard as the same arbitrary user[0]. The
                # web_app button populates signed initData so each guard is
                # identified by their own telegram_id. (Matches inline_kb.py.)
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=button_text,
                        web_app=WebAppInfo(url=webapp_url),
                    )],
                ])
            else:
                text += f"\n\n🌐 כניסה למערכת: {webapp_url}"
                kb = InlineKeyboardMarkup(inline_keyboard=[])
        else:
            # 2) No open week — check latest week status
            latest_week = await week_svc.get_latest_week()

            if latest_week is not None and latest_week.status == WeekStatus.LOCKED:
                text = f"שלום {display_name}! 👋\nהשבוע נעול — ההגשה נסגרה."
                kb = InlineKeyboardMarkup(inline_keyboard=[])
            elif latest_week is not None and latest_week.status == WeekStatus.CLOSED:
                text = f"שלום {display_name}! 👋\nההגשה סגורה כרגע."
                kb = InlineKeyboardMarkup(inline_keyboard=[])
            else:
                # Fallback — no week exists at all
                text = f"שלום {display_name}! 👋\nאין שבוע פעיל כרגע."
                kb = InlineKeyboardMarkup(inline_keyboard=[])

        await message.answer(text, reply_markup=kb)

        # The composed persistent bottom keyboard: punch row (ATTENDANCE_ENABLED)
        # + submit row (while a week is OPEN). A reply keyboard can't ride on
        # the inline-menu message above, so it gets a short message of its own.
        # Lazy import — same composition rule as main.py / bot_router.py.
        from app.bot.keyboards.reply_kb import main_reply_kb

        bottom_kb = await main_reply_kb()
        if bottom_kb is not None:
            await message.answer(
                "⚡ פעולות מהירות — בכפתורים הקבועים למטה",
                reply_markup=bottom_kb,
            )
    finally:
        try:
            await session_ctx.__aexit__(None, None, None)
        except Exception:
            pass


# ─── Callback: main menu ───────────────────────────────────

@router.callback_query(lambda c: c.data == "menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    # Re-use the same smart menu logic
    display_name = callback.from_user.first_name or "מאבטח"
    await _show_main_menu(callback.message, display_name)
    await callback.answer()


# ─── Callback: submit constraints ──────────────────────────

@router.callback_query(lambda c: c.data == "submit")
async def cb_submit(callback: CallbackQuery, state: FSMContext):
    """Start submission flow – find current open week."""
    _, week_svc, _, _ = await _get_services()

    week = await week_svc.get_current_open_week()
    if week is None:
        await callback.answer("אין שבוע פתוח להגשה כרגע.", show_alert=True)
        return

    await state.set_state(SubmissionFlow.selecting_days)
    await state.update_data(
        week_id=str(week.id),
        availabilities={},  # day_index -> bool
    )

    start = week.start_date
    end = week.end_date
    await callback.message.edit_text(
        f"📅 הגשת אילוצים לשבוע:\n{start} – {end}\n\n"
        "בחר יום לסימון זמינות:",
        reply_markup=weekday_kb(str(week.id)),
    )
    await callback.answer()


# ─── Callback: select a day ────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("day:"))
async def cb_select_day(callback: CallbackQuery, state: FSMContext):
    """Show availability options for a specific day."""
    parts = callback.data.split(":")
    week_id = parts[1]
    day_index = int(parts[2])
    day_name = DAY_NAMES[day_index]

    data = await state.get_data()
    availabilities = data.get("availabilities", {})
    current = availabilities.get(str(day_index))

    status_text = ""
    if current is True:
        status_text = " (✅ זמין)"
    elif current is False:
        status_text = " (❌ לא זמין)"

    await callback.message.edit_text(
        f"📅 יום {day_name}{status_text}\nבחר זמינות:",
        reply_markup=availability_kb(week_id, day_index),
    )
    await callback.answer()


# ─── Callback: set availability ────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("avail:"))
async def cb_set_availability(callback: CallbackQuery, state: FSMContext):
    """Record availability for a day."""
    parts = callback.data.split(":")
    week_id = parts[1]
    day_index = parts[2]
    available = parts[3] == "yes"

    data = await state.get_data()
    availabilities = data.get("availabilities", {})
    availabilities[day_index] = available
    await state.update_data(availabilities=availabilities)

    day_name = DAY_NAMES[int(day_index)]
    status = "✅ זמין" if available else "❌ לא זמין"
    await callback.answer(f"יום {day_name}: {status}", show_alert=False)

    # Refresh the day view
    await callback.message.edit_text(
        f"📅 יום {day_name} ({status})\nבחר זמינות:",
        reply_markup=availability_kb(week_id, int(day_index)),
    )


# ─── Callback: back to days list ───────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("backdays:"))
async def cb_back_to_days(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    week_id = parts[1]
    await callback.message.edit_text(
        "בחר יום לסימון זמינות:",
        reply_markup=weekday_kb(week_id),
    )
    await callback.answer()


# ─── Callback: finish submission ───────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("finish:"))
async def cb_finish(callback: CallbackQuery, state: FSMContext):
    """Submit the week's availability."""
    data = await state.get_data()
    week_id = data.get("week_id")
    availabilities = data.get("availabilities", {})
    telegram_id = callback.from_user.id

    if not availabilities:
        await callback.answer("לא בחרת זמינות לאף יום!", show_alert=True)
        return

    await state.clear()

    user_svc, _, sub_svc, session = await _get_services()
    user = await user_svc.get_by_telegram_id(telegram_id)
    if user is None:
        await callback.answer("שגיאה: משתמש לא נמצא. שלח /start.", show_alert=True)
        return

    # Build availability records list
    availability_records = []
    for day_str, avail in availabilities.items():
        availability_records.append({
            "day_index": int(day_str),
            "is_available": avail,
        })

    try:
        await sub_svc.submit_weekly(
            user_id=user.id,
            week_id=week_id,
            availability_records=availability_records,
        )
    except Exception as exc:
        logger.error("Bot submission failed: %s", exc)
        await callback.message.edit_text(
            "❌ שגיאה בשמירת האילוצים. נסה שוב.",
        )
        await callback.answer()
        return

    # Build summary
    lines = []
    for day_str, avail in sorted(availabilities.items(), key=lambda x: int(x[0])):
        name = DAY_NAMES[int(day_str)]
        status = "✅ זמין" if avail else "❌ לא זמין"
        lines.append(f"  {name}: {status}")

    await callback.message.edit_text(
        "✅ האילוצים נשמרו בהצלחה!\n\n" + "\n".join(lines),
    )
    await callback.answer()


# ─── Callback: status ──────────────────────────────────────

@router.callback_query(lambda c: c.data == "status")
async def cb_status(callback: CallbackQuery):
    """Show submission status for the current week."""
    _, week_svc, sub_svc, _ = await _get_services()

    week = await week_svc.get_current_open_week()
    if week is None:
        await callback.answer("אין שבוע פתוח כרגע.", show_alert=True)
        return

    user_svc, _, _, _ = await _get_services()
    user = await user_svc.get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("משתמש לא רשום. שלח /start.", show_alert=True)
        return

    submission = await sub_svc.get_submission(user.id, week.id)
    if submission is None:
        text = "📭 טרם הגשת אילוצים לשבוע הנוכחי."
    else:
        text = f"✅ הגשת אילוצים לשבוע {week.start_date}."

    await callback.message.edit_text(text)
    await callback.answer()


# ─── Callback: help ────────────────────────────────────────

@router.callback_query(lambda c: c.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ <b>עזרה - מערכת ניהול אילוצים</b>\n\n"
        "📅 <b>הגשת אילוצים</b> — סמן את הימים שבהם אתה זמין/לא זמין\n"
        "📊 <b>סטטוס אילוצים</b> — בדוק אם הגשת אילוצים לשבוע הנוכחי\n"
        "🌐 <b>כניסה למערכת</b> — פתח את המערכת בדפדפן\n\n"
        "לתמיכה נוספת פנה למנהל המערכת.",
    )
    await callback.answer()


# ─── Fallback ──────────────────────────────────────────────

@router.message()
async def fallback(message: Message, state: FSMContext):
    """Catch-all for unrecognized messages."""
    # If user is in phone verification, redirect
    current_state = await state.get_state()
    if current_state == PhoneVerification.waiting_for_phone:
        await message.answer(
            "נא לשלוח מספר טלפון בלבד (ללא מקף, ללא רווחים).\n\n"
            "לדוגמה: 0501234567"
        )
        return
    await message.answer("לא הבנתי. השתמש בתפריט או שלח /start.")