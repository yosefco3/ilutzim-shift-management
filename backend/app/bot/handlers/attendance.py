"""
Attendance bot handlers (stage 3) — GPS consent + the punch flow.

The guard experience, two taps total:
  1. Tap "🟢 החתמת כניסה" / "🔴 החתמת יציאה" on the persistent keyboard.
  2. Tap the native share-location button (Telegram pops its own confirmation).
→ "✅ נרשמה כניסה ב-07:12".

Consent gate: before the FIRST location request the guard confirms the
approved consent message once (timestamp on ``users.gps_consent_at``).

Design rule: nothing here fails silently — every wrong state (no consent, text
instead of location, double tap, unknown user) gets a clear Hebrew reply.

This router is included by ``bot_router`` only when ``ATTENDANCE_ENABLED`` is
on, so with the flag off none of these handlers exist.
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.attendance.constants import PunchDirection
from app.bot.keyboards.attendance import (
    BTN_CANCEL,
    BTN_PUNCH_IN,
    BTN_PUNCH_OUT,
    location_request_kb,
    punch_reply_kb,
)
from app.utils.date_utils import now_il

logger = logging.getLogger("ilutzim")

router = Router()


class PunchFlow(StatesGroup):
    """FSM: a punch button was tapped; waiting for the location share."""

    waiting_for_location = State()

CONSENT_CALLBACK = "att_gps_consent_ok"

# Approved wording (Yosef, 2026-07-04) — see STAGE_3_PROMPTS/01_telegram_punch/step_03.
GPS_CONSENT_TEXT = (
    "📍 <b>שיתוף מיקום להחתמת נוכחות</b>\n\n"
    "כדי להחתים כניסה ויציאה, האפליקציה מבקשת את מיקום הטלפון "
    "<b>ברגע ההחתמה בלבד</b>.\n"
    "המיקום משמש רק לאימות שההחתמה בוצעה באתר, נשמר יחד עם רישום "
    "הנוכחות שלך, וגלוי למנהל המערכת.\n"
    "<b>אין שום מעקב מיקום מעבר לרגע ההחתמה.</b>\n\n"
    "לחיצה על \"אני מאשר\" נדרשת פעם אחת בלבד."
)

CONSENT_THANKS_TEXT = (
    "✅ תודה! ההסכמה נשמרה.\n"
    "מעכשיו אפשר להחתים כניסה ויציאה מכפתורי ההחתמה."
)


def consent_kb() -> InlineKeyboardMarkup:
    """Single-button inline keyboard for the consent message."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ אני מאשר", callback_data=CONSENT_CALLBACK)]
        ]
    )


async def _get_user_session():
    """Fresh DB session + UserRepository for consent handlers.

    Mirrors ``core._get_services`` (caller commits). Split out so tests can
    patch it with an in-memory session.
    """
    from app.database import get_session
    from app.repositories.user_repository import UserRepository

    session_ctx = get_session()
    session = await session_ctx.__aenter__()
    return UserRepository(session), session


async def send_consent_request(message: Message) -> None:
    """Show the one-time consent message (called from the punch flow)."""
    await message.answer(GPS_CONSENT_TEXT, reply_markup=consent_kb())


@router.callback_query(F.data == CONSENT_CALLBACK)
async def on_consent_confirmed(callback: CallbackQuery) -> None:
    """Persist the consent timestamp for the tapping guard."""
    telegram_id = callback.from_user.id
    user_repo, session = await _get_user_session()
    try:
        user = await user_repo.get_by_telegram_id(str(telegram_id))
        if user is None:
            await callback.answer()
            await callback.message.answer(
                "לא מצאתי אותך במערכת — שלח /start כדי להירשם, ואז נסה שוב."
            )
            return

        if user.gps_consent_at is None:
            user.gps_consent_at = now_il().replace(tzinfo=None)
            await session.commit()
            logger.info("GPS consent recorded for user %s", user.id)

        await callback.answer("ההסכמה נשמרה ✅")
        await callback.message.answer(CONSENT_THANKS_TEXT, reply_markup=punch_reply_kb())
    finally:
        await session.close()


# ─── Punch flow ────────────────────────────────────────────

_DIRECTION_BY_BUTTON = {
    BTN_PUNCH_IN: PunchDirection.IN,
    BTN_PUNCH_OUT: PunchDirection.OUT,
}

_DIRECTION_LABEL = {
    PunchDirection.IN: "כניסה",
    PunchDirection.OUT: "יציאה",
}

_DIRECTION_ICON = {
    PunchDirection.IN: "🟢",
    PunchDirection.OUT: "🔴",
}

DIRECTION_CONFIRM_PREFIX = "att_dir:"
DIRECTION_CANCEL_CALLBACK = "att_dir_cancel"


def _direction_confirm_kb(
    *, suggested: PunchDirection, original: PunchDirection
) -> InlineKeyboardMarkup:
    """The "did you mean...?" keyboard — suggested fix first, then the
    original choice, then cancel. Explicit choice skips the mismatch check."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{_DIRECTION_ICON[suggested]} כן, החתם {_DIRECTION_LABEL[suggested]}",
                    callback_data=f"{DIRECTION_CONFIRM_PREFIX}{suggested.value}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{_DIRECTION_ICON[original]} לא, באמת {_DIRECTION_LABEL[original]}",
                    callback_data=f"{DIRECTION_CONFIRM_PREFIX}{original.value}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ ביטול", callback_data=DIRECTION_CANCEL_CALLBACK
                )
            ],
        ]
    )


async def _begin_location_flow(
    message: Message, state: FSMContext, direction: PunchDirection
) -> None:
    """Enter the waiting-for-location state and ask for the one-off share."""
    await state.set_state(PunchFlow.waiting_for_location)
    await state.update_data(punch_direction=direction.value)
    await message.answer(
        f"החתמת {_DIRECTION_LABEL[direction]} — כדי להשלים, שתף מיקום 👇",
        reply_markup=location_request_kb(),
    )


async def _get_punch_services():
    """Fresh DB session + (UserRepository, PunchService, session).

    Split out so tests can patch it. Caller must close the session.
    """
    from app.attendance.repositories.event_repository import AttendanceEventRepository
    from app.attendance.repositories.shift_repository import AttendanceShiftRepository
    from app.attendance.services.attendance_settings import get_attendance_config
    from app.attendance.services.pairing_service import PairingService
    from app.attendance.services.punch_service import PunchService
    from app.database import get_session
    from app.repositories.system_settings_repository import SystemSettingsRepository
    from app.repositories.user_repository import UserRepository
    from app.services.settings_service import SettingsService

    session_ctx = get_session()
    session = await session_ctx.__aenter__()
    config = await get_attendance_config(
        SettingsService(SystemSettingsRepository(session))
    )
    events_repo = AttendanceEventRepository(session)
    return (
        UserRepository(session),
        PunchService(events_repo, config),
        PairingService(events_repo, AttendanceShiftRepository(session)),
        session,
    )


@router.message(F.text.in_(set(_DIRECTION_BY_BUTTON)))
async def on_punch_button(message: Message, state: FSMContext) -> None:
    """Punch button tapped → consent gate → dedup gate → ask for location.

    The dedup check runs HERE, before the location request: if this direction
    was already recorded minutes ago there is nothing to complete, so the
    guard gets "already recorded" immediately instead of being asked to share
    a location for nothing.
    """
    direction = _DIRECTION_BY_BUTTON[message.text]
    user_repo, punch_service, _pairing, session = await _get_punch_services()
    try:
        user = await user_repo.get_by_telegram_id(str(message.from_user.id))
        if user is None:
            await message.answer(
                "לא מצאתי אותך במערכת — שלח /start כדי להירשם, ואז נסה שוב."
            )
            return

        if user.gps_consent_at is None:
            await send_consent_request(message)
            return

        duplicate = await punch_service.find_recent_duplicate(
            user.id, direction, now_il().replace(tzinfo=None)
        )
        if duplicate is not None:
            await message.answer(
                f"כבר נרשמה {_DIRECTION_LABEL[direction]} "
                f"ב-{duplicate.punched_at.strftime('%H:%M')} ✔",
                reply_markup=punch_reply_kb(),
            )
            return

        # Smart direction confirmation (step 06): a button that contradicts
        # the current shift state gets a "did you mean...?" prompt instead of
        # silently creating an in-in / orphan-out mess for the admin.
        open_shift = await _pairing.latest_open_shift(user.id)
        if direction == PunchDirection.IN and open_shift is not None:
            await message.answer(
                f"אתה כבר במשמרת (כניסה ב-"
                f"{open_shift.check_in_at.strftime('%H:%M')}). "
                "אולי התכוונת ליציאה?",
                reply_markup=_direction_confirm_kb(
                    suggested=PunchDirection.OUT, original=PunchDirection.IN
                ),
            )
            return
        if direction == PunchDirection.OUT and open_shift is None:
            await message.answer(
                "לא רשומה לך כניסה פתוחה. אולי התכוונת לכניסה?",
                reply_markup=_direction_confirm_kb(
                    suggested=PunchDirection.IN, original=PunchDirection.OUT
                ),
            )
            return
    finally:
        await session.close()

    await _begin_location_flow(message, state, direction)


@router.callback_query(F.data.startswith(DIRECTION_CONFIRM_PREFIX))
async def on_direction_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    """The guard explicitly chose a direction from the "did you mean" prompt.

    No mismatch re-check (the choice is explicit) — but the dedup gate still
    applies to the CHOSEN direction.
    """
    direction = PunchDirection(callback.data.removeprefix(DIRECTION_CONFIRM_PREFIX))
    await callback.answer()

    user_repo, punch_service, _pairing, session = await _get_punch_services()
    try:
        user = await user_repo.get_by_telegram_id(str(callback.from_user.id))
        if user is None:
            await callback.message.answer(
                "לא מצאתי אותך במערכת — שלח /start כדי להירשם."
            )
            return

        duplicate = await punch_service.find_recent_duplicate(
            user.id, direction, now_il().replace(tzinfo=None)
        )
        if duplicate is not None:
            await callback.message.answer(
                f"כבר נרשמה {_DIRECTION_LABEL[direction]} "
                f"ב-{duplicate.punched_at.strftime('%H:%M')} ✔",
                reply_markup=punch_reply_kb(),
            )
            return
    finally:
        await session.close()

    await _begin_location_flow(callback.message, state, direction)


@router.callback_query(F.data == DIRECTION_CANCEL_CALLBACK)
async def on_direction_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel from the "did you mean" prompt — nothing recorded."""
    await callback.answer()
    await state.clear()
    await callback.message.answer("ההחתמה בוטלה.", reply_markup=punch_reply_kb())


@router.message(PunchFlow.waiting_for_location, F.location)
async def on_punch_location(message: Message, state: FSMContext) -> None:
    """Location received → record the punch and confirm."""
    data = await state.get_data()
    await state.clear()
    direction = PunchDirection(data.get("punch_direction", PunchDirection.IN.value))
    label = _DIRECTION_LABEL[direction]

    user_repo, punch_service, pairing_service, session = await _get_punch_services()
    try:
        user = await user_repo.get_by_telegram_id(str(message.from_user.id))
        if user is None:
            await message.answer(
                "לא מצאתי אותך במערכת — שלח /start כדי להירשם.",
                reply_markup=punch_reply_kb(),
            )
            return

        punched_at = now_il().replace(tzinfo=None)
        outcome = await punch_service.record_punch(
            user.id,
            direction,
            punched_at,
            lat=message.location.latitude,
            lng=message.location.longitude,
            accuracy_m=getattr(message.location, "horizontal_accuracy", None),
        )
        if outcome.created:
            # Keep the derived shifts in step with the log (idempotent).
            await pairing_service.recompute_for_punch(user.id, punched_at)
        await session.commit()
    except Exception:
        logger.exception("Punch recording failed for tg=%s", message.from_user.id)
        await message.answer(
            "משהו השתבש ברישום ההחתמה 😕 נסה שוב, ואם זה חוזר — פנה למנהל.",
            reply_markup=punch_reply_kb(),
        )
        return
    finally:
        await session.close()

    hhmm = outcome.event.punched_at.strftime("%H:%M")
    if not outcome.created:
        await message.answer(
            f"כבר נרשמה {label} ב-{hhmm} ✔", reply_markup=punch_reply_kb()
        )
        return

    text = f"✅ נרשמה {label} ב-{hhmm}"
    if outcome.event.out_of_radius:
        km = (outcome.event.distance_from_site_m or 0) / 1000
        text += f"\n⚠️ ההחתמה נקלטה מחוץ לטווח האתר ({km:.1f} ק\"מ) — היא נרשמה וסומנה."
    await message.answer(text, reply_markup=punch_reply_kb())


@router.message(PunchFlow.waiting_for_location, F.text == BTN_CANCEL)
async def on_punch_cancel(message: Message, state: FSMContext) -> None:
    """Cancel → back to the persistent punch keyboard."""
    await state.clear()
    await message.answer("ההחתמה בוטלה.", reply_markup=punch_reply_kb())


@router.message(PunchFlow.waiting_for_location)
async def on_punch_not_location(message: Message) -> None:
    """Anything that isn't a location while we wait → gentle re-prompt."""
    await message.answer(
        "כדי להשלים את ההחתמה יש לשתף מיקום דרך הכפתור 👇 (או ללחוץ ביטול)",
        reply_markup=location_request_kb(),
    )
