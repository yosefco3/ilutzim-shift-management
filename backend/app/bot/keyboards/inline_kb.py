"""
Inline keyboards for the Telegram bot (Hebrew UI).
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

# Hebrew weekday names
DAY_NAMES = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]


def main_menu_kb() -> InlineKeyboardMarkup:
    """Main menu after /start.

    The 'נהלים' (procedures) entry is appended only when PROCEDURES_ENABLED is
    on, so with the flag off the menu is unchanged and the button cannot lead
    to an unregistered handler.
    """
    rows = [
        [InlineKeyboardButton(text="📅 הגשת אילוצים", callback_data="submit")],
        [InlineKeyboardButton(text="📊 סטטוס אילוצים", callback_data="status")],
        [InlineKeyboardButton(text="ℹ️ עזרה", callback_data="help")],
    ]
    from app.bot.keyboards.procedures import main_menu_procedures_button

    btn = main_menu_procedures_button()
    if btn is not None:
        rows.append([btn])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def weekday_kb(week_id: str) -> InlineKeyboardMarkup:
    """Day selector keyboard for a given week."""
    buttons = []
    for i, name in enumerate(DAY_NAMES):
        buttons.append([InlineKeyboardButton(
            text=f"📅 יום {name}",
            callback_data=f"day:{week_id}:{i}",
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ סיום ושליחה",
        callback_data=f"finish:{week_id}",
    )])
    buttons.append([InlineKeyboardButton(
        text="🔙 חזרה לתפריט",
        callback_data="menu",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def availability_kb(week_id: str, day_index: int) -> InlineKeyboardMarkup:
    """Availability selector for a specific day."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ זמין",
            callback_data=f"avail:{week_id}:{day_index}:yes",
        )],
        [InlineKeyboardButton(
            text="❌ לא זמין",
            callback_data=f"avail:{week_id}:{day_index}:no",
        )],
        [InlineKeyboardButton(
            text="🔙 חזרה לימים",
            callback_data=f"backdays:{week_id}",
        )],
    ])


def submission_success_kb() -> InlineKeyboardMarkup:
    """Inline keyboard shown after successful submission."""
    from app.bot.webapp import submit_webapp_url
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✏️ ערוך אילוצים",
            web_app=WebAppInfo(url=submit_webapp_url()),
        )],
    ])


def submit_constraints_kb() -> InlineKeyboardMarkup:
    """Inline keyboard with a WebApp button to fill in constraints."""
    from app.bot.webapp import submit_webapp_url
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📅 הגשת אילוצים",
            web_app=WebAppInfo(url=submit_webapp_url()),
        )],
    ])
