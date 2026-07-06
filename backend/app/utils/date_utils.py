"""Date utilities for the Week Workflow feature.

Guards always submit constraints for the upcoming Sunday through Saturday.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings


def now_il() -> datetime:
    """Timezone-aware 'now' in the scheduler timezone (Asia/Jerusalem by default).

    Single source of truth for the server's notion of the current instant. Use
    this — never a naive ``datetime.now()`` — anywhere the weekly rollover reasons
    about "which week is current", because the container clock is UTC in prod and
    a naive ``today()`` still reads Saturday at the Sunday-00:00-IL rollover (B-3).
    Do NOT use for ``timestamp without time zone`` columns (e.g. ``opened_at``) —
    asyncpg rejects tz-aware values there.
    """
    return datetime.now(ZoneInfo(get_settings().SCHEDULER_TIMEZONE))


def today_il() -> date:
    """Today's date in the scheduler timezone — use everywhere the weekly rollover
    reasons about 'which week is current'."""
    return now_il().date()


def upcoming_sunday(today: date = None) -> date:
    """Return the next Sunday strictly in the future.

    If today is Sunday → return next week's Sunday (+7 days).

    Args:
        today: The reference date. Defaults to date.today().

    Returns:
        The next upcoming Sunday.
    """
    if today is None:
        today = date.today()

    days_ahead = (6 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # today is Sunday, skip to next
    return today + timedelta(days=days_ahead)


def get_next_week_start(current_start: date) -> date:
    """Next week starts 7 days after current week's start_date."""
    return current_start + timedelta(days=7)


def get_next_week_end(next_start: date) -> date:
    """6 days after next_start (= next Saturday)."""
    return next_start + timedelta(days=6)


def week_range(today: date = None) -> tuple[date, date]:
    """Return the (sunday, saturday) tuple for the upcoming guard week.

    Args:
        today: The reference date. Defaults to date.today().

    Returns:
        A tuple of (upcoming_sunday, upcoming_saturday).
    """
    sunday = upcoming_sunday(today)
    return (sunday, sunday + timedelta(days=6))