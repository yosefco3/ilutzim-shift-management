"""
PairingService — turns the raw punch log into paired actual shifts.

The delicate heart of stage 3 / 01. Rules (all locked 2026-07-04):

- An IN opens a shift; the next OUT within ``MAX_SHIFT_HOURS`` closes it
  (``COMPLETE``). A night shift crossing midnight is attributed to the day the
  IN happened (``work_date``).
- IN followed by another IN → the first becomes ``MISSING_OUT`` (forgot to
  punch out), the second opens a new shift.
- An OUT with no open shift (or too far from its IN) is an **orphan**: it is
  skipped here and left for the comparison layer to surface as an anomaly —
  the raw log always keeps it.
- A trailing IN is ``OPEN`` while ``now - in <= MAX_SHIFT_HOURS``, else
  ``MISSING_OUT``.

**Idempotent by construction**: recomputing a window deletes its derived rows
and rebuilds them from the log, so running it twice is a no-op. The window is
widened one day back so a midnight-crossing OUT always finds its IN.
"""

import logging
import uuid
from datetime import date, datetime, time, timedelta

from app.attendance.constants import (
    MAX_SHIFT_HOURS,
    PunchDirection,
    ShiftPairStatus,
)
from app.attendance.models.attendance_event import AttendanceEvent
from app.attendance.models.attendance_shift import AttendanceShift
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository

logger = logging.getLogger("ilutzim")

_MAX_SHIFT = timedelta(hours=MAX_SHIFT_HOURS)


class PairingService:
    """Recomputes ``attendance_shifts`` windows from ``attendance_events``."""

    def __init__(
        self,
        events: AttendanceEventRepository,
        shifts: AttendanceShiftRepository,
    ) -> None:
        self._events = events
        self._shifts = shifts

    async def recompute_user(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
        *,
        now: datetime,
    ) -> list[AttendanceShift]:
        """Rebuild the user's shifts whose work_date ∈ [date_from-1, date_to]."""
        window_start = date_from - timedelta(days=1)
        scan_from = datetime.combine(window_start, time.min)
        # Scan far enough past date_to that a night shift STARTING on date_to
        # finds its OUT (which lands the next morning).
        scan_to = datetime.combine(date_to + timedelta(days=1), time.min) + _MAX_SHIFT

        # Effective events only — punches voided/edited by the admin are
        # superseded and must not shape the derived shifts.
        events = await self._events.list_effective_for_user(
            user_id, scan_from, scan_to
        )
        await self._shifts.delete_window(user_id, window_start, date_to)

        pairs = self._pair(events, boundary=date_to, now=now)

        rows: list[AttendanceShift] = []
        for in_ev, out_ev, status in pairs:
            work_date = in_ev.punched_at.date()
            if not (window_start <= work_date <= date_to):
                continue  # belongs to a neighboring window's recompute
            rows.append(
                await self._shifts.create(
                    user_id=user_id,
                    work_date=work_date,
                    check_in_at=in_ev.punched_at,
                    check_out_at=out_ev.punched_at if out_ev else None,
                    in_event_id=in_ev.id,
                    out_event_id=out_ev.id if out_ev else None,
                    status=status,
                    recomputed_at=now,
                )
            )
        return rows

    @staticmethod
    def _pair(
        events: list[AttendanceEvent], *, boundary: date, now: datetime
    ) -> list[tuple[AttendanceEvent, AttendanceEvent | None, ShiftPairStatus]]:
        """The core pairing pass (pure — no I/O)."""
        pairs: list[tuple[AttendanceEvent, AttendanceEvent | None, ShiftPairStatus]] = []
        open_in: AttendanceEvent | None = None

        for ev in events:
            if ev.direction == PunchDirection.IN:
                if open_in is not None:
                    # in-in: the first shift lost its out punch.
                    pairs.append((open_in, None, ShiftPairStatus.MISSING_OUT))
                    open_in = None
                if ev.punched_at.date() > boundary:
                    # A future-window IN — only OUTs beyond the boundary may
                    # serve this window (to close its last shift). Stop here.
                    break
                open_in = ev
            else:  # OUT
                if open_in is None:
                    logger.info(
                        "Pairing: orphan OUT skipped (user=%s at=%s)",
                        ev.user_id, ev.punched_at,
                    )
                    continue
                delta = ev.punched_at - open_in.punched_at
                if timedelta(0) <= delta <= _MAX_SHIFT:
                    pairs.append((open_in, ev, ShiftPairStatus.COMPLETE))
                else:
                    # OUT too far from its IN: close the shift without it and
                    # let the OUT surface as an orphan anomaly.
                    pairs.append((open_in, None, ShiftPairStatus.MISSING_OUT))
                    logger.info(
                        "Pairing: OUT beyond %sh skipped (user=%s at=%s)",
                        MAX_SHIFT_HOURS, ev.user_id, ev.punched_at,
                    )
                open_in = None

        if open_in is not None:
            still_plausible = now - open_in.punched_at <= _MAX_SHIFT
            pairs.append(
                (
                    open_in,
                    None,
                    ShiftPairStatus.OPEN if still_plausible else ShiftPairStatus.MISSING_OUT,
                )
            )
        return pairs

    async def latest_open_shift(self, user_id: uuid.UUID) -> AttendanceShift | None:
        """The user's current OPEN shift (None = not checked in). Bot-facing."""
        return await self._shifts.latest_open_for_user(user_id)

    async def recompute_for_punch(
        self, user_id: uuid.UUID, punched_at: datetime
    ) -> None:
        """Targeted recompute after a single new punch (bot write path)."""
        day = punched_at.date()
        await self.recompute_user(user_id, day, day, now=punched_at)

    async def daily_sweep(self, *, now: datetime) -> None:
        """Scheduler job body: refresh the recent window for everyone active,
        then flip any long-stale OPEN shifts (outside the window) to MISSING_OUT."""
        today = now.date()
        yesterday = today - timedelta(days=1)
        user_ids = await self._events.distinct_user_ids(
            datetime.combine(yesterday - timedelta(days=1), time.min),
            now,
        )
        for user_id in user_ids:
            await self.recompute_user(user_id, yesterday, today, now=now)
        flipped = await self._shifts.close_stale_open(now - _MAX_SHIFT, now)
        if flipped:
            logger.info("Attendance sweep: %d stale open shifts → missing_out", flipped)
