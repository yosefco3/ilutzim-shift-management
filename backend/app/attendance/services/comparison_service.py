"""
ComparisonService — planned-vs-actual, classified per minute (stage 3 / 02).

The heart of the admin UI. For each user-day it produces:

- ``planned``   — the guard's windows from the built schedule (consumed via
  ``ScheduleExportService.get_week_schedule().by_guard`` so the attendance
  page, the Telegram broadcast and the Excel exports can never disagree).
- ``actual``    — the paired shifts (raw check-in; check-out shown both raw
  and quarter-rounded — the rounded value is what totals/payroll use).
- ``segments``  — every minute of the day's timeline classified:
  ``covered`` / ``gap_small`` / ``gap_big`` / ``extra`` / ``no_show`` /
  ``future``. **The future is never a gap**: classification stops at ``now``.
- ``summary``   — the dry numbers (Δin, Δout, totals) + one Hebrew tag +
  a severity for the two-tier color language (big=bold, small=light).

No recommendations anywhere — the admin sees, the admin decides (4/7).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type, datetime, time, timedelta

from app.attendance.constants import PunchDirection, PunchSource, ShiftPairStatus
from app.attendance.models.attendance_shift import AttendanceShift
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.utils import dt_intervals as di
from app.attendance.utils.rounding import round_out_up_quarter
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.services.schedule_export_service import (
    ScheduleExportService,
    WeekSchedule,
)

logger = logging.getLogger("ilutzim")

# Segment kinds (the visual vocabulary of the timeline bars).
KIND_COVERED = "covered"
KIND_GAP_SMALL = "gap_small"
KIND_GAP_BIG = "gap_big"
KIND_EXTRA = "extra"
KIND_NO_SHOW = "no_show"
KIND_FUTURE = "future"

# Display bands, matching the board's morning/evening/night strips.
BAND_MORNING = "morning"
BAND_EVENING = "evening"
BAND_NIGHT = "night"


@dataclass(frozen=True)
class PlannedWindow:
    position_name: str
    start: datetime
    end: datetime  # > start; a night window ends on the next calendar day
    is_event: bool = False


@dataclass(frozen=True)
class ActualView:
    """A paired shift as the UI consumes it."""

    shift_id: uuid.UUID
    check_in_at: datetime
    check_out_raw: datetime | None
    check_out_rounded: datetime | None
    status: ShiftPairStatus
    in_source: str | None
    out_source: str | None
    out_of_radius: bool
    # Raw event ids — the edit dialog targets punches by these.
    in_event_id: uuid.UUID | None = None
    out_event_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    kind: str


@dataclass(frozen=True)
class OrphanOut:
    """An OUT punch no shift consumed (out-without-in) — carries the raw
    event id so the edit dialog can fix/void it like any paired punch."""

    event_id: uuid.UUID
    punched_at: datetime
    source: str | None


@dataclass(frozen=True)
class DaySummary:
    planned_minutes: int
    actual_minutes: int          # rounded-out based (what payroll counts)
    extra_minutes: int           # presence beyond the plan
    delta_in_minutes: int | None   # + = late, - = early (first in vs first plan)
    delta_out_minutes: int | None  # + = stayed late, - = left early
    severity: str                # 'big' | 'small' | 'ok' | 'none'
    tag: str                     # short Hebrew status label
    orphan_out_times: list[str] = field(default_factory=list)
    orphan_outs: list[OrphanOut] = field(default_factory=list)


@dataclass(frozen=True)
class UserDayComparison:
    user_id: uuid.UUID
    user_name: str
    date: date_type
    band: str
    planned: list[PlannedWindow]
    actual: list[ActualView]
    segments: list[Segment]
    summary: DaySummary


class ComparisonService:
    """Builds per-day / per-period planned-vs-actual comparisons."""

    def __init__(
        self,
        weeks: ScheduleWeekRepository,
        users: UserRepository,
        shifts: AttendanceShiftRepository,
        events: AttendanceEventRepository,
        # Any WeekSchedule source: ScheduleExportService (the frozen plan) or
        # ActualScheduleExportService (the editable execution copy) — picked by
        # the ACTUAL_SCHEDULE_ENABLED flag in attendance/dependencies.
        export: ScheduleExportService,
        config: AttendanceConfig,
        adjustments=None,  # AttendanceAdjustmentRepository | None (absence approvals)
    ) -> None:
        self._weeks = weeks
        self._users = users
        self._shifts = shifts
        self._events = events
        self._export = export
        self._config = config
        self._adjustments = adjustments
        self._week_cache: dict[uuid.UUID, WeekSchedule] = {}

    @property
    def config(self) -> AttendanceConfig:
        """The parsed attendance config (shared with the alerts job)."""
        return self._config

    # ── public API ───────────────────────────────────────────────────────────

    async def get_day_all(self, day: date_type, *, now: datetime) -> dict:
        """Everyone relevant on ``day``: scheduled OR punched — including a
        guard whose only record is an orphan OUT (a punch that paired into no
        shift must still surface, not vanish). Extra unscheduled guards simply
        show their punch hours with no planned lane."""
        planned_map = await self._planned_map_for_date(day)
        shifts = await self._shifts.list_by_date_with_events(day)
        shifts_by_user: dict[uuid.UUID, list[AttendanceShift]] = {}
        for s in shifts:
            shifts_by_user.setdefault(s.user_id, []).append(s)

        # Names for EVERYONE (an inactive guard who punched must not render as
        # "לא ידוע" — attendance records facts about whoever made them).
        names = {
            u.id: u.full_name
            for u in await self._users.get_all(limit=10_000)
        }
        day_start = datetime.combine(day, time.min)
        punched_ids = set(
            await self._events.distinct_user_ids(
                day_start, day_start + timedelta(days=1)
            )
        )
        user_ids = set(planned_map) | set(shifts_by_user) | punched_ids

        rows: list[UserDayComparison] = []
        for user_id in user_ids:
            rows.append(
                await self._build_user_day(
                    user_id,
                    names.get(user_id, "לא ידוע"),
                    day,
                    planned_map.get(user_id, []),
                    shifts_by_user.get(user_id, []),
                    now=now,
                )
            )
        rows.sort(key=lambda r: (_SEVERITY_ORDER.get(r.summary.severity, 9), r.user_name))
        return {
            "date": day,
            "now": now,
            "counters": {
                "scheduled": sum(1 for r in rows if r.planned),
                "present": sum(1 for r in rows if r.actual),
                "big": sum(1 for r in rows if r.summary.severity == "big"),
                "small": sum(1 for r in rows if r.summary.severity == "small"),
            },
            "rows": rows,
        }

    async def get_user_day(
        self, user_id: uuid.UUID, day: date_type, *, now: datetime
    ) -> UserDayComparison:
        planned_map = await self._planned_map_for_date(day)
        shifts = await self._shifts.list_for_user_with_events(user_id, day, day)
        user = await self._users.get_by_id(user_id)
        return await self._build_user_day(
            user_id,
            user.full_name if user else "לא ידוע",
            day,
            planned_map.get(user_id, []),
            shifts,
            now=now,
        )

    async def get_user_period(
        self,
        user_id: uuid.UUID,
        date_from: date_type,
        date_to: date_type,
        *,
        now: datetime,
    ) -> dict:
        """The employee page feed: only days with a plan or a punch, plus a
        period summary."""
        user = await self._users.get_by_id(user_id)
        name = user.full_name if user else "לא ידוע"
        shifts = await self._shifts.list_for_user_with_events(
            user_id, date_from, date_to
        )
        shifts_by_day: dict[date_type, list[AttendanceShift]] = {}
        for s in shifts:
            shifts_by_day.setdefault(s.work_date, []).append(s)

        # Days with punches that produced NO shift (e.g. an orphan OUT) must
        # still appear — otherwise the incident is invisible on the page.
        event_days = set(
            await self._events.event_dates_for_user(user_id, date_from, date_to)
        )

        days: list[UserDayComparison] = []
        day = date_from
        while day <= date_to:
            planned = (await self._planned_map_for_date(day)).get(user_id, [])
            day_shifts = shifts_by_day.get(day, [])
            if planned or day_shifts or day in event_days:
                days.append(
                    await self._build_user_day(
                        user_id, name, day, planned, day_shifts, now=now
                    )
                )
            day = day + timedelta(days=1)

        return {
            "user_id": user_id,
            "user_name": name,
            "from": date_from,
            "to": date_to,
            "days": days,
            "summary": {
                "planned_minutes": sum(d.summary.planned_minutes for d in days),
                "actual_minutes": sum(d.summary.actual_minutes for d in days),
                "extra_minutes": sum(d.summary.extra_minutes for d in days),
                "big": sum(1 for d in days if d.summary.severity == "big"),
                "small": sum(1 for d in days if d.summary.severity == "small"),
            },
        }

    async def get_period_summary(
        self, date_from: date_type, date_to: date_type, *, now: datetime
    ) -> list[dict]:
        """Per-employee aggregates over a range — the main page's week/month
        list. One line per employee who was scheduled or punched at least once."""
        acc: dict[uuid.UUID, dict] = {}
        day = date_from
        while day <= date_to:
            day_data = await self.get_day_all(day, now=now)
            for row in day_data["rows"]:
                entry = acc.setdefault(
                    row.user_id,
                    {
                        "user_id": row.user_id,
                        "user_name": row.user_name,
                        "planned_minutes": 0,
                        "actual_minutes": 0,
                        "extra_minutes": 0,
                        "days_scheduled": 0,
                        "days_present": 0,
                        "big": 0,
                        "small": 0,
                    },
                )
                s = row.summary
                entry["planned_minutes"] += s.planned_minutes
                entry["actual_minutes"] += s.actual_minutes
                entry["extra_minutes"] += s.extra_minutes
                entry["days_scheduled"] += 1 if row.planned else 0
                entry["days_present"] += 1 if row.actual else 0
                entry["big"] += 1 if s.severity == "big" else 0
                entry["small"] += 1 if s.severity == "small" else 0
            day = day + timedelta(days=1)

        rows = list(acc.values())
        rows.sort(key=lambda r: (-r["big"], -r["small"], r["user_name"]))
        return rows

    # ── planned side ─────────────────────────────────────────────────────────

    async def _planned_map_for_date(
        self, day: date_type
    ) -> dict[uuid.UUID, list[PlannedWindow]]:
        """user_id → planned windows on ``day`` (from the week's built board)."""
        week = await self._weeks.get_week_containing(day)
        if week is None:
            return {}
        schedule = await self._week_schedule(week.id)
        iso = day.isoformat()
        out: dict[uuid.UUID, list[PlannedWindow]] = {}
        for guard in schedule.by_guard:
            windows = []
            for shift in guard.shifts:
                if shift.date != iso:
                    continue
                start = datetime.combine(day, _parse_hhmm(shift.start))
                end = datetime.combine(day, _parse_hhmm(shift.end))
                if end <= start:  # crosses midnight
                    end += timedelta(days=1)
                windows.append(
                    PlannedWindow(
                        position_name=shift.position_name,
                        start=start,
                        end=end,
                        is_event=shift.is_event,
                    )
                )
            if windows:
                out[guard.user_id] = sorted(windows, key=lambda w: w.start)
        return out

    async def _week_schedule(self, week_id: uuid.UUID) -> WeekSchedule:
        if week_id not in self._week_cache:
            self._week_cache[week_id] = await self._export.get_week_schedule(week_id)
        return self._week_cache[week_id]

    # ── the classifier ───────────────────────────────────────────────────────

    async def _build_user_day(
        self,
        user_id: uuid.UUID,
        user_name: str,
        day: date_type,
        planned: list[PlannedWindow],
        shifts: list[AttendanceShift],
        *,
        now: datetime,
    ) -> UserDayComparison:
        actual_views = [_to_view(s, now) for s in shifts]

        p_iv = [(w.start, w.end) for w in planned]
        # Geometry uses RAW ends (the honest picture). An OPEN shift runs to
        # now (still on site). A MISSING_OUT shift contributes NO interval
        # (decision 4/7, option 1): with no verified end there is no verified
        # presence — the planned window shows as an uncovered gap, the punch
        # marker shows the IN, and the totals count 0 until the admin fixes it.
        a_iv = []
        for v in actual_views:
            if v.check_out_raw is not None:
                end = v.check_out_raw
            elif v.status == ShiftPairStatus.OPEN:
                end = min(now, v.check_in_at + timedelta(hours=16))
            else:  # MISSING_OUT — unverified, uncounted
                continue
            if end > v.check_in_at:
                a_iv.append((v.check_in_at, end))

        past_p = di.intersect(p_iv, [(datetime.min, now)])
        future = di.subtract(p_iv, [(datetime.min, now)])
        covered = di.intersect(past_p, a_iv)
        gaps = di.subtract(past_p, a_iv)
        extra = di.subtract(a_iv, p_iv)

        segments: list[Segment] = []
        # No-show = never punched at all. A MISSING_OUT shift has no counted
        # interval but the guard DID arrive — that day is "אין יציאה", not "לא הגיע".
        no_show = bool(past_p) and not actual_views
        # An admin-approved absence clears the anomaly: the no-show day drops
        # back to neutral color and carries an ✎ tag instead of red.
        absence_approved = False
        if no_show and self._adjustments is not None:
            absence_approved = await self._adjustments.has_absence_approval(
                user_id, day
            )
        for s, e in covered:
            segments.append(Segment(s, e, KIND_COVERED))
        for s, e in gaps:
            gap_min = (e - s).total_seconds() / 60
            if no_show:
                kind = KIND_FUTURE if absence_approved else KIND_NO_SHOW
            elif gap_min <= self._config.grace_minutes:
                kind = KIND_COVERED  # within grace — not an anomaly
            elif gap_min <= self._config.big_gap_minutes:
                kind = KIND_GAP_SMALL
            else:
                kind = KIND_GAP_BIG
            segments.append(Segment(s, e, kind))
        for s, e in extra:
            segments.append(Segment(s, e, KIND_EXTRA))
        for s, e in future:
            segments.append(Segment(s, e, KIND_FUTURE))
        segments.sort(key=lambda seg: seg.start)

        orphan_outs = await self._orphan_outs(user_id, day, shifts)
        summary = self._summarize(
            planned, actual_views, segments, orphan_outs, now=now,
            absence_approved=absence_approved,
        )
        return UserDayComparison(
            user_id=user_id,
            user_name=user_name,
            date=day,
            band=_band_for(planned, actual_views),
            planned=planned,
            actual=actual_views,
            segments=segments,
            summary=summary,
        )

    async def _orphan_outs(
        self, user_id: uuid.UUID, day: date_type, shifts: list[AttendanceShift]
    ) -> list[OrphanOut]:
        """OUT punches on ``day`` that no shift consumed (out-without-in)."""
        day_start = datetime.combine(day, time.min)
        events = await self._events.list_effective_for_user(
            user_id, day_start, day_start + timedelta(days=1)
        )
        used = {s.out_event_id for s in shifts if s.out_event_id}
        # An OUT belonging to the PREVIOUS day's night shift is used by that
        # shift (different work_date) — collect used ids from yesterday too.
        prev = await self._shifts.list_for_user(
            user_id, day - timedelta(days=1), day - timedelta(days=1)
        )
        used |= {s.out_event_id for s in prev if s.out_event_id}
        return [
            OrphanOut(
                event_id=e.id,
                punched_at=e.punched_at,
                source=e.source.value if e.source else None,
            )
            for e in events
            if e.direction == PunchDirection.OUT and e.id not in used
        ]

    def _summarize(
        self,
        planned: list[PlannedWindow],
        actual: list[ActualView],
        segments: list[Segment],
        orphan_outs: list[OrphanOut],
        *,
        now: datetime,
        absence_approved: bool = False,
    ) -> DaySummary:
        orphan_times = [o.punched_at.strftime("%H:%M") for o in orphan_outs]
        kinds = {s.kind for s in segments}
        planned_minutes = di.total_minutes([(w.start, w.end) for w in planned])
        actual_minutes = 0
        for v in actual:
            if v.check_out_rounded is not None:
                end = v.check_out_rounded
            elif v.status == ShiftPairStatus.OPEN:
                end = min(now, v.check_in_at + timedelta(hours=16))
            else:  # MISSING_OUT counts 0 until the admin completes the out
                continue
            actual_minutes += max(0, int((end - v.check_in_at).total_seconds() // 60))
        extra_minutes = sum(
            int((s.end - s.start).total_seconds() // 60)
            for s in segments
            if s.kind == KIND_EXTRA
        )

        delta_in = delta_out = None
        if planned and actual:
            delta_in = int(
                (actual[0].check_in_at - planned[0].start).total_seconds() // 60
            )
            last_out = actual[-1].check_out_raw
            if last_out is not None:
                delta_out = int(
                    (last_out - planned[-1].end).total_seconds() // 60
                )

        missing_out = any(
            v.status == ShiftPairStatus.MISSING_OUT for v in actual
        )
        out_of_radius = any(v.out_of_radius for v in actual)

        if absence_approved and not actual:
            severity, tag = "ok", "היעדרות מאושרת ✎"
        elif KIND_NO_SHOW in kinds:
            severity, tag = "big", "לא הגיע"
        elif missing_out or orphan_times or KIND_GAP_BIG in kinds:
            severity = "big"
            if missing_out:
                tag = "אין יציאה"
            elif orphan_times:
                tag = "יציאה בלי כניסה"
            else:
                tag = "פער גדול"
        elif KIND_GAP_SMALL in kinds or out_of_radius:
            severity = "small"
            if KIND_GAP_SMALL in kinds and delta_in is not None and delta_in > self._config.grace_minutes:
                tag = f"איחור {delta_in} ד'"
            elif out_of_radius:
                tag = "מחוץ לטווח האתר"
            else:
                tag = "פער קטן"
        elif actual and not planned:
            severity, tag = "small", "ללא שיבוץ"
        elif planned and not actual and not any(
            s.kind != KIND_FUTURE for s in segments
        ):
            severity, tag = "none", "טרם התחיל"
        elif actual and any(v.status == ShiftPairStatus.OPEN for v in actual):
            severity, tag = "ok", "בעמדה ✔"
        elif actual:
            severity, tag = "ok", "תקין ✔"
        else:
            severity, tag = "none", "—"

        return DaySummary(
            planned_minutes=planned_minutes,
            actual_minutes=actual_minutes,
            extra_minutes=extra_minutes,
            delta_in_minutes=delta_in,
            delta_out_minutes=delta_out,
            severity=severity,
            tag=tag,
            orphan_out_times=orphan_times,
            orphan_outs=orphan_outs,
        )


_SEVERITY_ORDER = {"big": 0, "small": 1, "ok": 2, "none": 3}


def _parse_hhmm(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _to_view(shift: AttendanceShift, now: datetime) -> ActualView:
    in_ev = shift.in_event
    out_ev = shift.out_event
    # Quarter-up rounding applies to raw device/telegram punches ONLY — an
    # admin-entered check-out is final exactly as typed (decision 4/7).
    if shift.check_out_at is None:
        rounded = None
    elif out_ev is not None and out_ev.source == PunchSource.MANUAL:
        rounded = shift.check_out_at
    else:
        rounded = round_out_up_quarter(shift.check_out_at)
    return ActualView(
        shift_id=shift.id,
        check_in_at=shift.check_in_at,
        check_out_raw=shift.check_out_at,
        check_out_rounded=rounded,
        status=shift.status,
        in_source=in_ev.source.value if in_ev else None,
        out_source=out_ev.source.value if out_ev else None,
        out_of_radius=bool(
            (in_ev and in_ev.out_of_radius) or (out_ev and out_ev.out_of_radius)
        ),
        in_event_id=shift.in_event_id,
        out_event_id=shift.out_event_id,
    )


def _band_for(planned: list[PlannedWindow], actual: list[ActualView]) -> str:
    """Morning/evening/night strip, by the planned (else actual) start hour —
    the same coarse bands the board uses for its display strips."""
    if planned:
        hour = planned[0].start.hour
    elif actual:
        hour = actual[0].check_in_at.hour
    else:
        return BAND_MORNING
    if 5 <= hour < 12:
        return BAND_MORNING
    if 12 <= hour < 20:
        return BAND_EVENING
    return BAND_NIGHT
