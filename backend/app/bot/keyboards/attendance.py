"""
Attendance punch keyboards (stage 3).

Two keyboards:
- ``punch_reply_kb`` — the PERSISTENT bottom keyboard with the two punch
  buttons. Always visible for active guards while the feature is on, so a
  punch is never more than two taps away.
- ``location_request_kb`` — a one-time keyboard shown after a punch button is
  tapped: a native share-location button (Telegram pops its own confirmation)
  plus a cancel button.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_PUNCH_IN = "🟢 החתמת כניסה"
BTN_PUNCH_OUT = "🔴 החתמת יציאה"
BTN_SHARE_LOCATION = "📍 שתף מיקום להחתמה"
BTN_CANCEL = "❌ ביטול"


def punch_reply_kb() -> ReplyKeyboardMarkup:
    """The persistent two-button punch keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PUNCH_IN), KeyboardButton(text=BTN_PUNCH_OUT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="החתמת נוכחות",
    )


def location_request_kb() -> ReplyKeyboardMarkup:
    """One-time keyboard: share location (native) or cancel."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SHARE_LOCATION, request_location=True)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
