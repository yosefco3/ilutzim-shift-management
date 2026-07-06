"""
Pure parsing helpers for the week auto open/lock settings.

These turn the string-valued admin settings (weekday name, "HH:MM" time,
"true"/"false") into typed values usable by APScheduler. They never touch the
DB and never raise on bad input — invalid input is logged and a safe default is
returned, so a typo in the settings can't crash the scheduler (a disabled /
default job is safer than a boot failure).
"""

import logging

logger = logging.getLogger("ilutzim")

# Full English weekday names and abbreviations → APScheduler CronTrigger tokens.
_WEEKDAYS = {
    "sunday": "sun", "sun": "sun",
    "monday": "mon", "mon": "mon",
    "tuesday": "tue", "tue": "tue",
    "wednesday": "wed", "wed": "wed",
    "thursday": "thu", "thu": "thu",
    "friday": "fri", "fri": "fri",
    "saturday": "sat", "sat": "sat",
}


def parse_weekday(value: str, default: str = "sun") -> str:
    """Map a weekday name/abbreviation to an APScheduler day_of_week token.

    Case-insensitive. Returns ``default`` (logged) on unrecognised input.
    """
    token = _WEEKDAYS.get(str(value or "").strip().lower())
    if token is None:
        logger.warning("Invalid weekday setting %r — falling back to %r", value, default)
        return default
    return token


def parse_hhmm(value: str, default: tuple[int, int] = (0, 0)) -> tuple[int, int]:
    """Parse an "HH:MM" string into a validated (hour, minute) tuple.

    Returns ``default`` (logged) on malformed input or out-of-range values.
    """
    try:
        hh, mm = str(value).strip().split(":")
        hour, minute = int(hh), int(mm)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        raise ValueError("out of range")
    except (ValueError, AttributeError):
        logger.warning("Invalid HH:MM setting %r — falling back to %r", value, default)
        return default


def as_bool(value, default: bool = False) -> bool:
    """Interpret a stored setting value as a boolean.

    Accepts real booleans and the string forms used by the settings layer
    ("true"/"false"/"1"/"0", case-insensitive). Falls back to ``default``.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return default
