"""
AlertService — the three admin Telegram alerts (stage 3 / 02, expanded 4/7):

- 🔴 no_show     — a scheduled shift started more than grace minutes ago and
                   the guard has no punch at all that day.
- 🟠 long_shift  — more than ``long_shift_hours`` between check-in and
                   check-out — or until *now* for a still-open shift (the
                   important case: the guard is STILL on site).
- 🟡 short_rest  — less than ``min_rest_hours`` between the previous shift's
                   check-out (raw) and the current check-in. Skipped when the
                   previous shift has no check-out (nothing to measure).

A threshold of 0 disables that specific check. Each incident alerts exactly
once — the ``attendance_alerts_sent`` unique key is the idempotency ledger.
Sending is best-effort via the existing bot notifications path.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.attendance.models.attendance_alert_sent import AttendanceAlertSent
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.services.comparison_service import ComparisonService

logger = logging.getLogger("ilutzim")

ALERT_NO_SHOW = "no_show"
ALERT_LONG_SHIFT = "long_shift"
ALERT_SHORT_REST = "short_rest"


class AlertService:
    """Detects incidents, dedups them, and messages the admin."""

    def __init__(
        self,
        comparison: ComparisonService,
        shifts: AttendanceShiftRepository,
        config: AttendanceConfig,
        session,
        send,  # async callable (chat_id, text) — injected for testability
    ) -> None:
        self._comparison = comparison
        self._shifts = shifts
        self._config = config
        self._session = session
        self._send = send

    async def run_checks(self, *, now: datetime) -> int:
        """Run all three checks; returns how many alerts were dispatched."""
        if not self._config.admin_alerts_enabled or not self._config.admin_chat_id:
            return 0

        candidates: list[tuple[str, uuid.UUID, str, str]] = []
        today = now.date()
        yesterday = today - timedelta(days=1)

        # A single classified pass over yesterday+today feeds all checks
        # (yesterday catches night shifts and cross-midnight rests).
        rows = []
        for day in (yesterday, today):
            rows.extend((await self._comparison.get_day_all(day, now=now))["rows"])

        candidates += self._no_show_candidates(rows, now)
        candidates += self._long_shift_candidates(rows, now)
        candidates += await self._short_rest_candidates(rows, now)

        sent = 0
        for alert_type, user_id, ref_key, text in candidates:
            if await self._mark_once(alert_type, user_id, ref_key, now):
                try:
                    await self._send(self._config.admin_chat_id, text)
                    sent += 1
                except Exception as exc:  # best-effort — never kill the job
                    logger.warning("Attendance alert send failed: %s", exc)
        return sent

    # ── checks ───────────────────────────────────────────────────────────────

    def _no_show_candidates(self, rows, now):
        out = []
        grace = timedelta(minutes=self._config.grace_minutes)
        for row in rows:
            if row.actual or not row.planned:
                continue
            if row.summary.tag == "היעדרות מאושרת ✎":
                continue  # the admin already handled it
            for window in row.planned:
                if window.start + grace < now:
                    out.append((
                        ALERT_NO_SHOW,
                        row.user_id,
                        f"{row.date.isoformat()}:{window.start.strftime('%H:%M')}",
                        f"🔴 {row.user_name} לא החתים כניסה — "
                        f"{window.position_name}, משמרת {window.start.strftime('%H:%M')}",
                    ))
        return out

    def _long_shift_candidates(self, rows, now):
        hours = self._config.long_shift_hours
        if hours <= 0:
            return []
        limit = timedelta(hours=hours)
        out = []
        for row in rows:
            for shift in row.actual:
                end = shift.check_out_raw or now
                length = end - shift.check_in_at
                if length <= limit:
                    continue
                start_hhmm = shift.check_in_at.strftime('%H:%M')
                if shift.check_out_raw is None:
                    detail = f"(כניסה {start_hhmm}, עדיין לא החתים יציאה)"
                else:
                    detail = (
                        f"(כניסה {start_hhmm}, יציאה "
                        f"{shift.check_out_raw.strftime('%H:%M')})"
                    )
                out.append((
                    ALERT_LONG_SHIFT,
                    row.user_id,
                    str(shift.shift_id),
                    f"🟠 {row.user_name} במשמרת מעל {hours} שעות {detail}",
                ))
        return out

    async def _short_rest_candidates(self, rows, now):
        hours = self._config.min_rest_hours
        if hours <= 0:
            return []
        minimum = timedelta(hours=hours)
        out = []
        seen_users = {row.user_id: row.user_name for row in rows if row.actual}
        for user_id, user_name in seen_users.items():
            # Chronological shifts over the last few days — raw check-out feeds
            # the rest measurement (decision: rounding is payroll-only).
            shifts = await self._shifts.list_for_user(
                user_id, now.date() - timedelta(days=3), now.date()
            )
            for prev, curr in zip(shifts, shifts[1:]):
                if prev.check_out_at is None:
                    continue  # nothing to measure against
                rest = curr.check_in_at - prev.check_out_at
                if timedelta(0) <= rest < minimum:
                    hh = int(rest.total_seconds() // 3600)
                    mm = int((rest.total_seconds() % 3600) // 60)
                    out.append((
                        ALERT_SHORT_REST,
                        user_id,
                        str(curr.id),
                        f"🟡 {user_name} נכנס למשמרת אחרי {hh}:{mm:02d} שעות "
                        f"מנוחה בלבד (יצא {prev.check_out_at.strftime('%H:%M')}, "
                        f"נכנס {curr.check_in_at.strftime('%H:%M')})",
                    ))
        return out

    # ── idempotency ──────────────────────────────────────────────────────────

    async def _mark_once(
        self, alert_type: str, user_id: uuid.UUID, ref_key: str, now: datetime
    ) -> bool:
        """Insert the ledger row; False when this incident already alerted.

        Select-first keeps the normal path rollback-free (a mid-run rollback
        would discard earlier flushed ledger rows); the unique constraint
        remains the hard backstop.
        """
        from sqlalchemy import select

        existing = await self._session.execute(
            select(AttendanceAlertSent.id)
            .where(
                AttendanceAlertSent.alert_type == alert_type,
                AttendanceAlertSent.user_id == user_id,
                AttendanceAlertSent.ref_key == ref_key,
            )
            .limit(1)
        )
        if existing.scalars().first() is not None:
            return False

        self._session.add(
            AttendanceAlertSent(
                alert_type=alert_type,
                user_id=user_id,
                ref_date=now.date(),
                ref_key=ref_key,
            )
        )
        try:
            await self._session.flush()
            return True
        except IntegrityError:
            await self._session.rollback()
            return False
