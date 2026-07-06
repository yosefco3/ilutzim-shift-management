"""
Demo-history seeder (stage 3 / 02.5) — DEV ONLY.

Propagates a believable attendance history into the weeks BEFORE the upcoming
real week: two small demo profiles (A=15 positions, B=17), full schedules per
past week, and punches with a realistic anomaly mix. Everything it creates is
surgically removable:

- every demo punch carries ``note='DEMO'`` (cascade removes derived shifts);
- the demo profiles are named with a ``(DEMO)`` suffix — deleting them cascades
  their positions, schedule assignments and week↔profile links.

HARD BOUNDARY (decision 4/7): the upcoming week (currently 2026-07-05 →
2026-07-11) and anything after it are NEVER touched — they carry the real
profile and schedule. Asserted in code, not just promised.

The entry point (``run``) refuses to run outside ``ENVIRONMENT=dev``.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete as sa_delete, select

from app.attendance.constants import PunchDirection, PunchSource
from app.attendance.models.attendance_event import AttendanceEvent
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.pairing_service import PairingService
from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment

logger = logging.getLogger("ilutzim")

DEMO_NOTE = "DEMO"
DEMO_PROFILE_A = "דמו נוכחות A (DEMO)"
DEMO_PROFILE_B = "דמו נוכחות B (DEMO)"

# Anomaly mix (cumulative thresholds over rng.random()).
P_NO_SHOW = 0.04
P_MISSING_OUT = 0.09
P_LATE = 0.16
P_EARLY_LEAVE = 0.18

KIND_NORMAL = "normal"
KIND_NO_SHOW = "no_show"
KIND_MISSING_OUT = "missing_out"
KIND_LATE = "late"
KIND_EARLY_LEAVE = "early_leave"


# ── pure helpers (unit-tested) ───────────────────────────────────────────────

def profile_a_positions() -> list[tuple[str, dict]]:
    """15 positions: 7 morning, 4 evening, 3 night (midnight-crossing), 1 odd."""
    all_days = [str(d) for d in range(7)]
    weekdays = [str(d) for d in range(6)]  # ראשון–שישי

    def days(day_list, start, end):
        return {d: {"start": start, "end": end} for d in day_list}

    out: list[tuple[str, dict]] = []
    for i in range(1, 7):  # 6 בוקר מלאים
        out.append((f"עמדת בוקר {i}", days(all_days, "07:00", "15:00")))
    out.append(("בוקר חלקי", days(weekdays, "07:00", "15:00")))            # 7
    for i in range(1, 5):  # 4 ערב
        out.append((f"עמדת ערב {i}", days(all_days, "15:00", "23:00")))
    for i in range(1, 4):  # 3 לילה — חוצה חצות
        out.append((f"סיור לילה {i}", days(all_days, "23:00", "07:00")))
    out.append(("שער מוקדם", days(weekdays, "06:00", "14:00")))            # 15
    return out


def profile_b_positions() -> list[tuple[str, dict]]:
    """17 positions: profile A's base + one more evening patrol + a short
    morning post, with a couple of small hour tweaks."""
    base = profile_a_positions()
    tweaked = []
    for name, sched in base:
        if name == "עמדת ערב 1":  # small hour difference vs A
            sched = {d: {"start": "14:30", "end": "22:30"} for d in sched}
        tweaked.append((name, sched))
    all_days = [str(d) for d in range(7)]
    tweaked.append(("סיור ערב נוסף", {d: {"start": "16:00", "end": "23:00"} for d in all_days}))
    tweaked.append(("בוקר קצר", {d: {"start": "08:00", "end": "12:00"} for d in ["0", "2", "4"]}))
    return tweaked


def anomaly_kind(rng: random.Random) -> str:
    roll = rng.random()
    if roll < P_NO_SHOW:
        return KIND_NO_SHOW
    if roll < P_MISSING_OUT:
        return KIND_MISSING_OUT
    if roll < P_LATE:
        return KIND_LATE
    if roll < P_EARLY_LEAVE:
        return KIND_EARLY_LEAVE
    return KIND_NORMAL


def window_datetimes(day: date, start_hhmm: str, end_hhmm: str) -> tuple[datetime, datetime]:
    """Absolute window; end <= start crosses midnight into the next day."""
    sh, sm = (int(x) for x in start_hhmm.split(":"))
    eh, em = (int(x) for x in end_hhmm.split(":"))
    start = datetime.combine(day, time(sh, sm))
    end = datetime.combine(day, time(eh, em))
    if end <= start:
        end += timedelta(days=1)
    return start, end


def punch_times(
    kind: str, start: datetime, end: datetime, rng: random.Random
) -> list[tuple[PunchDirection, datetime]]:
    """The punches a demo guard makes for one assigned shift."""
    if kind == KIND_NO_SHOW:
        return []
    minute = timedelta(minutes=1)
    if kind == KIND_LATE:
        check_in = start + minute * rng.randint(20, 50)
    else:
        check_in = start + minute * rng.randint(-8, 12)
    punches = [(PunchDirection.IN, check_in)]
    if kind == KIND_MISSING_OUT:
        return punches
    if kind == KIND_EARLY_LEAVE:
        check_out = end - minute * rng.randint(30, 90)
    else:
        check_out = end + minute * rng.randint(0, 20)
    if check_out > check_in:
        punches.append((PunchDirection.OUT, check_out))
    return punches


def demo_week_starts(upcoming_start: date, weeks: int) -> list[date]:
    """Sunday start-dates of the demo weeks — strictly before the upcoming week."""
    starts = [upcoming_start - timedelta(days=7 * i) for i in range(weeks, 0, -1)]
    for s in starts:
        assert s + timedelta(days=6) < upcoming_start, "demo week crosses the hard boundary"
    return starts


# ── seeding engine ───────────────────────────────────────────────────────────

@dataclass
class SeedReport:
    weeks: int = 0
    positions_a: int = 0
    positions_b: int = 0
    assignments: int = 0
    events: int = 0
    kinds: dict = field(default_factory=dict)

    def count_kind(self, kind: str) -> None:
        self.kinds[kind] = self.kinds.get(kind, 0) + 1


async def wipe_demo(session) -> dict:
    """Remove ALL demo artifacts: DEMO punches (cascade drops their derived
    shifts) and the (DEMO) profiles (cascade drops positions, assignments and
    week↔profile links). Real data is untouched."""
    events_result = await session.execute(
        sa_delete(AttendanceEvent).where(AttendanceEvent.note == DEMO_NOTE)
    )
    profiles = (
        await session.execute(
            select(ActivationProfile).where(ActivationProfile.name.like("%(DEMO)%"))
        )
    ).scalars().all()
    for profile in profiles:
        await session.delete(profile)
    await session.flush()
    return {"events_deleted": events_result.rowcount or 0, "profiles_deleted": len(profiles)}


async def _ensure_profile(session, name: str, positions: list[tuple[str, dict]]) -> ActivationProfile:
    existing = (
        await session.execute(
            select(ActivationProfile).where(ActivationProfile.name == name)
        )
    ).scalars().first()
    if existing is not None:
        return existing
    profile = ActivationProfile(
        name=name,
        kind="דמו",
        description="נוצר אוטומטית ע\"י seed_attendance_demo — נמחק ב---wipe",
        is_default=False,
        display_order=99,
    )
    session.add(profile)
    await session.flush()
    for order, (pos_name, day_schedules) in enumerate(positions):
        session.add(
            Position(
                profile_id=profile.id,
                name=pos_name,
                day_schedules=day_schedules,
                required_attributes=[],
                display_order=order,
            )
        )
    await session.flush()
    return profile


async def _ensure_week(session, start: date) -> ScheduleWeek:
    end = start + timedelta(days=6)
    existing = (
        await session.execute(
            select(ScheduleWeek).where(ScheduleWeek.start_date == start)
        )
    ).scalars().first()
    if existing is not None:
        return existing
    week = ScheduleWeek(start_date=start, end_date=end, status=WeekStatus.LOCKED)
    session.add(week)
    await session.flush()
    return week


async def seed_demo_history(
    session, *, upcoming_start: date, weeks: int = 8, seed: int = 42
) -> SeedReport:
    """The core engine (dev-gate lives in ``run``; tests call this directly)."""
    rng = random.Random(seed)
    report = SeedReport()

    await wipe_demo(session)  # idempotent re-runs

    guards = (
        await session.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.created_at)
        )
    ).scalars().all()
    if not guards:
        raise RuntimeError("אין שומרים פעילים — אין על מי לזרוע נוכחות")

    profile_a = await _ensure_profile(session, DEMO_PROFILE_A, profile_a_positions())
    profile_b = await _ensure_profile(session, DEMO_PROFILE_B, profile_b_positions())
    report.positions_a = len(profile_a_positions())
    report.positions_b = len(profile_b_positions())

    events_repo = AttendanceEventRepository(session)
    pairing = PairingService(events_repo, AttendanceShiftRepository(session))
    touched_users: set = set()
    week_starts = demo_week_starts(upcoming_start, weeks)

    for week_index, start in enumerate(week_starts):
        week = await _ensure_week(session, start)
        assert week.end_date < upcoming_start  # the hard boundary, enforced
        profile = profile_a if week_index % 2 == 0 else profile_b
        # week ↔ profile (replace any previous demo link)
        await session.execute(
            sa_delete(WeekProfileAssignment).where(
                WeekProfileAssignment.week_id == week.id
            )
        )
        session.add(WeekProfileAssignment(week_id=week.id, profile_id=profile.id))

        positions = (
            await session.execute(
                select(Position)
                .where(Position.profile_id == profile.id)
                .order_by(Position.display_order)
            )
        ).scalars().all()

        evening_enders: dict[tuple[int, object], datetime] = {}
        for day_offset in range(7):
            day = start + timedelta(days=day_offset)
            pool = guards[:]
            rng.shuffle(pool)
            for position in positions:
                hours = position.day_schedules.get(str(day_offset))
                if not hours or not pool:
                    continue  # inactive day, or more positions than guards
                guard = pool.pop()
                session.add(
                    ScheduleAssignment(
                        week_id=week.id,
                        position_id=position.id,
                        day_index=day_offset,
                        user_id=guard.id,
                    )
                )
                report.assignments += 1

                win_start, win_end = window_datetimes(day, hours["start"], hours["end"])
                kind = anomaly_kind(rng)
                report.count_kind(kind)
                for direction, at in punch_times(kind, win_start, win_end, rng):
                    await events_repo.add(
                        user_id=guard.id,
                        direction=direction,
                        punched_at=at,
                        source=PunchSource.TELEGRAM,
                        note=DEMO_NOTE,
                    )
                    report.events += 1
                if kind != KIND_NO_SHOW:
                    touched_users.add(guard.id)
                if win_end.time() == time(23, 0):
                    evening_enders[(day_offset, guard.id)] = win_end

        # Weekly color: one unscheduled presence + one forced short-rest.
        if len(guards) > 1:
            stray = rng.choice(guards)
            stray_day = start + timedelta(days=rng.randint(0, 6))
            stray_in = datetime.combine(stray_day, time(10, 0))
            for direction, at in [
                (PunchDirection.IN, stray_in),
                (PunchDirection.OUT, stray_in + timedelta(hours=rng.randint(3, 5))),
            ]:
                await events_repo.add(
                    user_id=stray.id,
                    direction=direction,
                    punched_at=at,
                    source=PunchSource.TELEGRAM,
                    note=DEMO_NOTE,
                )
                report.events += 1
            touched_users.add(stray.id)
        for (day_offset, guard_id), out_at in list(evening_enders.items())[:1]:
            # came back at ~04:45 after a 23:00 exit → a 5:45 rest incident
            early_in = out_at + timedelta(hours=5, minutes=45)
            await events_repo.add(
                user_id=guard_id,
                direction=PunchDirection.IN,
                punched_at=early_in,
                source=PunchSource.TELEGRAM,
                note=DEMO_NOTE,
            )
            await events_repo.add(
                user_id=guard_id,
                direction=PunchDirection.OUT,
                punched_at=early_in + timedelta(hours=3),
                source=PunchSource.TELEGRAM,
                note=DEMO_NOTE,
            )
            report.events += 2
            touched_users.add(guard_id)

        report.weeks += 1

    await session.flush()

    # Pair everything once, over the whole demo range.
    range_start = week_starts[0]
    range_end = upcoming_start - timedelta(days=1)
    recompute_now = datetime.combine(upcoming_start, time(12, 0))
    for user_id in touched_users:
        await pairing.recompute_user(
            user_id, range_start, range_end, now=recompute_now
        )
    return report


async def run(*, weeks: int = 8, wipe_only: bool = False, seed: int = 42) -> None:
    """CLI entry — dev-gated, own committed session, prints a summary."""
    from app.config import get_settings

    if get_settings().ENVIRONMENT != "dev":
        raise SystemExit(
            "seed_attendance_demo רץ רק בסביבת dev (ENVIRONMENT=dev) — בוטל."
        )

    from app.database import get_session
    from app.utils.date_utils import today_il, week_range

    upcoming_start, _ = week_range(today_il())

    async with get_session() as session:
        if wipe_only:
            result = await wipe_demo(session)
            print(f"🧹 wipe: {result['events_deleted']} אירועי דמו, "
                  f"{result['profiles_deleted']} פרופילי דמו — נמחקו")
            return
        report = await seed_demo_history(
            session, upcoming_start=upcoming_start, weeks=weeks, seed=seed
        )

    print("✅ נזרעה היסטוריית דמו:")
    print(f"   גבול קשיח: לא נגענו בשבוע {upcoming_start} ואילך")
    print(f"   שבועות: {report.weeks} · פרופילים: A={report.positions_a} עמדות, "
          f"B={report.positions_b} עמדות")
    print(f"   שיבוצים: {report.assignments} · אירועי החתמה: {report.events}")
    print(f"   פילוח: {report.kinds}")
