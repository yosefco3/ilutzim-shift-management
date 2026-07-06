"""
Attendance domain constants.
"""

import enum


class PunchDirection(str, enum.Enum):
    """Direction of a single punch."""

    IN = "in"
    OUT = "out"


class PunchSource(str, enum.Enum):
    """Where a punch came from.

    TELEGRAM — the guard pressed the punch keyboard in the existing bot and
    shared a one-off location. MANUAL — the admin entered/corrected it in the
    admin UI (always carries an audit record). DEVICE — reserved for the future
    physical clock (ZKTeco); no code path produces it yet.
    """

    TELEGRAM = "telegram"
    MANUAL = "manual"
    DEVICE = "device"


class ShiftPairStatus(str, enum.Enum):
    """Lifecycle of a paired actual-shift row (derived from the raw log)."""

    COMPLETE = "complete"        # has both check-in and check-out
    OPEN = "open"                # check-in only, plausibly still on shift
    MISSING_OUT = "missing_out"  # check-in only, shift clearly over — no out punch


class AdjustmentAction(str, enum.Enum):
    """What an admin correction did (the audit trail's verb).

    EDIT_TIME    — replaced a punch's timestamp (original voided, a MANUAL
                   replacement event appended; `before`/`after` hold both).
    ADD_PUNCH    — appended a missing punch as a MANUAL event.
    VOID_PUNCH   — logically cancelled a wrong punch (the raw row stays).
    MARK_ABSENCE — approved a no-show day (clears its anomaly color).
    """

    EDIT_TIME = "edit_time"
    ADD_PUNCH = "add_punch"
    VOID_PUNCH = "void_punch"
    MARK_ABSENCE = "mark_absence"


# A second punch in the SAME direction within this window is treated as a
# double-tap and ignored (the guard gets a friendly "already recorded" reply).
PUNCH_DEDUP_WINDOW_MINUTES = 5

# Sanity ceiling for a single shift. An open shift older than this is no
# longer "still on duty" — it becomes MISSING_OUT; an OUT punch further than
# this from its IN will not close it (treated as an orphan instead).
MAX_SHIFT_HOURS = 16
