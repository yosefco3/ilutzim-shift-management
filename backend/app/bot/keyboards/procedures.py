"""
Inline keyboards for the procedure-quiz bot flow (סד"פ).

Callback-data convention ("prefix:params", matching the rest of the bot):
  - proc:menu          — open / back to the procedures list
  - proc:list:{page}   — paginate the list (10 per page)
  - proc:view:{id}     — view one procedure + start-quiz button
  - סדפ:quiz:{id}       — start (or retake) a quiz (same handler: a fresh attempt)

The start-quiz callback is reused for retakes: both create a new sampled
attempt, so one handler covers both. A passed procedure shows a ✅ marker.
"""

import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

PROC_MENU_CB = "proc:menu"
PROC_LIST_PREFIX = "proc:list:"
PROC_VIEW_PREFIX = "proc:view:"
QUIZ_START_PREFIX = "סדפ:quiz:"

PAGE_SIZE = 10


def start_quiz_kb(procedure_id) -> InlineKeyboardMarkup:
    """The 'start quiz' button (also used for retakes)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="▶️ התחל מבחן",
                callback_data=f"{QUIZ_START_PREFIX}{procedure_id}",
            )]
        ]
    )


def retake_kb(procedure_id) -> InlineKeyboardMarkup:
    """The 'retake' button — same callback as start (a fresh attempt)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔁 מבחן חוזר",
                callback_data=f"{QUIZ_START_PREFIX}{procedure_id}",
            )]
        ]
    )


def order_and_mark_procedures(procedures) -> list[tuple[str, str]]:
    """Order published procedures for the bot list and build ``(id, label)`` items.

    The default procedure (``is_default``) leads the list with a ⭐ marker on its
    button; the rest keep the newest-first order returned by
    ``ProcedureRepository.list_published``. Returns the full ordered item list;
    the caller paginates it.
    """
    default = next((p for p in procedures if getattr(p, "is_default", False)), None)
    if default is not None:
        ordered = [default] + [p for p in procedures if p.id != default.id]
    else:
        ordered = list(procedures)
    return [
        (
            str(p.id),
            ("⭐ " + p.title) if getattr(p, "is_default", False) else p.title,
        )
        for p in ordered
    ]


def procedures_list_kb(
    items: list[tuple[str, str]], page: int = 0, total: int = 0
) -> InlineKeyboardMarkup:
    """Paginated list of PUBLISHED procedures.

    ``items`` is a list of ``(procedure_id_str, title)`` for the current page.
    Prev/next buttons appear only when there is more than one page. The empty
    case is handled by the caller (which shows a plain text message), so this
    builder is never called with an empty list — every row it emits has a
    handled callback.
    """
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            text=title[:60],
            callback_data=f"{PROC_VIEW_PREFIX}{pid}",
        )]
        for pid, title in items
    ]

    nav: list[InlineKeyboardButton] = []
    last_page = max(0, (total - 1) // PAGE_SIZE) if total else 0
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ הקודם", callback_data=f"{PROC_LIST_PREFIX}{page - 1}"))
    if page < last_page:
        nav.append(InlineKeyboardButton(text="הבא ➡️", callback_data=f"{PROC_LIST_PREFIX}{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 חזרה לתפריט", callback_data=PROC_MENU_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def procedure_view_kb(procedure_id, *, passed: bool = False) -> InlineKeyboardMarkup:
    """View-procedure keyboard: start-quiz button (+ ✅ marker if passed)."""
    label = "✅ עברת — מבחן חוזר" if passed else "▶️ התחל מבחן"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=label,
                callback_data=f"{QUIZ_START_PREFIX}{procedure_id}",
            )],
            [InlineKeyboardButton(text="🔙 לרשימת הנהלים", callback_data=PROC_MENU_CB)],
        ]
    )


def main_menu_procedures_button() -> InlineKeyboardButton | None:
    """The 'נהלים' entry for the main menu (None when the feature is off).

    Gates the menu entry behind ``PROCEDURES_ENABLED`` so with the flag off the
    main menu is byte-for-byte unchanged.
    """
    from app.config import get_settings

    if not get_settings().PROCEDURES_ENABLED:
        return None
    return InlineKeyboardButton(text="📋 נהלים", callback_data=PROC_MENU_CB)
