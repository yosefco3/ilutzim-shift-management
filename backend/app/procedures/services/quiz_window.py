"""
Quiz availability window — pure time math, no I/O.

The admin bounds how long a published quiz stays startable via the
``procedure_quiz_window_days`` system setting (0 = unlimited). The window
anchor is ``Procedure.quiz_window_started_at`` — reset on every publish path,
including rebroadcast (that is how the admin "opens the quiz again"). Legacy
rows published before the anchor existed fall back to ``published_at``; both
None → no deadline (never lock a legacy quiz out by accident). [EDGE T2]

Everything here takes ``now`` as a parameter — callers pass naive Israel time
(``_now_naive()``), the same convention the anchors are stored in. [EDGE T1]

Only quiz START is gated (the caller: ``QuizService.start_attempt``); an
attempt already in progress may finish after expiry. [EDGE T3]
"""

from datetime import datetime, timedelta

from app.procedures.models.procedure import Procedure


def quiz_deadline(proc: Procedure, window_days: int) -> datetime | None:
    """The moment the quiz stops being startable, or None for no deadline."""
    if window_days <= 0:
        return None
    anchor = proc.quiz_window_started_at or proc.published_at
    if anchor is None:
        return None
    return anchor + timedelta(days=window_days)


def is_quiz_open(proc: Procedure, window_days: int, now: datetime) -> bool:
    """Whether a guard may still START the quiz at ``now``."""
    deadline = quiz_deadline(proc, window_days)
    return deadline is None or now <= deadline
