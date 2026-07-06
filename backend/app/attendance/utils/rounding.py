"""
Quarter-hour rounding (decision 2026-07-04, final):

- **Check-in** — exact, never rounded.
- **Check-out** — rounded UP to the next quarter hour: :01–:15 ⇒ :15,
  :16–:30 ⇒ :30, :31–:45 ⇒ :45, :46–:00 ⇒ :00. An exact quarter stays put.
- The raw punch is always stored and shown next to the rounded value; an
  admin-edited check-out is final and is NOT re-rounded (the edit layer marks
  it — this function is only applied to raw device/telegram punches).
"""

from datetime import datetime, timedelta

_QUARTER = 15 * 60  # seconds


def round_out_up_quarter(dt: datetime) -> datetime:
    """Round a check-out timestamp up to the next quarter hour."""
    base = dt.replace(minute=0, second=0, microsecond=0)
    seconds_in = (dt - base).total_seconds()
    quarters = int(-(-seconds_in // _QUARTER))  # ceil
    return base + timedelta(seconds=quarters * _QUARTER)
