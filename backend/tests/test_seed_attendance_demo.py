"""
Stage 3 / 02.5 step 1 — the demo-history seeder.
"""

import random
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.attendance.constants import PunchDirection, PunchSource
from app.attendance.dev_seed import (
    DEMO_NOTE,
    KIND_EARLY_LEAVE,
    KIND_LATE,
    KIND_MISSING_OUT,
    KIND_NO_SHOW,
    KIND_NORMAL,
    anomaly_kind,
    demo_week_starts,
    profile_a_positions,
    profile_b_positions,
    punch_times,
    seed_demo_history,
    wipe_demo,
    window_datetimes,
)
from app.attendance.models.attendance_event import AttendanceEvent
from app.attendance.models.attendance_shift import AttendanceShift
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment

UPCOMING = date(2026, 7, 5)  # the protected real week's Sunday


# ---------- pure helpers ----------

def test_profiles_have_15_and_17_positions():
    a = profile_a_positions()
    b = profile_b_positions()
    assert len(a) == 15
    assert len(b) == 17
    # night positions cross midnight
    night = dict(a)["סיור לילה 1"]
    assert night["0"] == {"start": "23:00", "end": "07:00"}


def test_window_datetimes_crosses_midnight():
    start, end = window_datetimes(date(2026, 6, 1), "23:00", "07:00")
    assert end == datetime(2026, 6, 2, 7, 0)
    start, end = window_datetimes(date(2026, 6, 1), "07:00", "15:00")
    assert end == datetime(2026, 6, 1, 15, 0)


def test_punch_times_by_kind():
    rng = random.Random(1)
    start = datetime(2026, 6, 1, 7, 0)
    end = datetime(2026, 6, 1, 15, 0)

    assert punch_times(KIND_NO_SHOW, start, end, rng) == []

    only_in = punch_times(KIND_MISSING_OUT, start, end, rng)
    assert [d for d, _ in only_in] == [PunchDirection.IN]

    late = punch_times(KIND_LATE, start, end, rng)
    assert timedelta(minutes=20) <= late[0][1] - start <= timedelta(minutes=50)

    early = punch_times(KIND_EARLY_LEAVE, start, end, rng)
    assert timedelta(minutes=30) <= end - early[1][1] <= timedelta(minutes=90)

    normal = punch_times(KIND_NORMAL, start, end, rng)
    assert len(normal) == 2 and normal[1][1] >= end


def test_anomaly_mix_is_realistic():
    rng = random.Random(7)
    kinds = [anomaly_kind(rng) for _ in range(2000)]
    share = kinds.count(KIND_NORMAL) / len(kinds)
    assert 0.75 < share < 0.88  # ~82% clean
    for k in (KIND_NO_SHOW, KIND_MISSING_OUT, KIND_LATE, KIND_EARLY_LEAVE):
        assert kinds.count(k) > 0


def test_demo_week_starts_respect_hard_boundary():
    starts = demo_week_starts(UPCOMING, 8)
    assert len(starts) == 8
    assert starts[-1] == UPCOMING - timedelta(days=7)
    assert all(s + timedelta(days=6) < UPCOMING for s in starts)
    assert starts == sorted(starts)


# ---------- engine (db) ----------

async def _guards(db_session, n=6):
    out = []
    for i in range(n):
        user = User(
            phone_number=f"05011122{i:02d}",
            first_name=f"שומר{i}",
            last_name="דמו",
            roles=[],
        )
        db_session.add(user)
        out.append(user)
    await db_session.commit()
    return out


async def _real_week_with_data(db_session, guard):
    """The protected upcoming week, with a 'real' punch that must survive."""
    week = ScheduleWeek(
        start_date=UPCOMING, end_date=UPCOMING + timedelta(days=6),
        status=WeekStatus.CLOSED,
    )
    db_session.add(week)
    real_event = await AttendanceEventRepository(db_session).add(
        user_id=guard.id,
        direction=PunchDirection.IN,
        punched_at=datetime(2026, 7, 5, 7, 0),
        source=PunchSource.TELEGRAM,
        note=None,
    )
    await db_session.commit()
    return week, real_event


@pytest.mark.asyncio
async def test_seed_creates_weeks_profiles_schedules_and_punches(db_session):
    guards = await _guards(db_session)
    report = await seed_demo_history(
        db_session, upcoming_start=UPCOMING, weeks=4, seed=42
    )
    await db_session.commit()

    assert report.weeks == 4
    assert report.assignments > 0
    assert report.events > 0

    # weeks created LOCKED, all strictly before the boundary
    weeks = (await db_session.execute(select(ScheduleWeek))).scalars().all()
    for w in weeks:
        assert w.end_date < UPCOMING
        assert w.status == WeekStatus.LOCKED

    # both demo profiles exist with the right position counts
    profiles = (
        await db_session.execute(
            select(ActivationProfile).where(ActivationProfile.name.like("%(DEMO)%"))
        )
    ).scalars().all()
    by_name = {}
    for p in profiles:
        positions = (
            await db_session.execute(
                select(Position).where(Position.profile_id == p.id)
            )
        ).scalars().all()
        by_name[p.name] = len(positions)
    assert set(by_name.values()) == {15, 17}
    assert all(not p.is_default for p in profiles)

    # punches are DEMO-tagged and paired into shifts
    events = (await db_session.execute(select(AttendanceEvent))).scalars().all()
    assert events and all(e.note == DEMO_NOTE for e in events)
    shifts = (await db_session.execute(select(AttendanceShift))).scalars().all()
    assert shifts

    # no guard is double-booked on the same week+day
    assignments = (
        await db_session.execute(select(ScheduleAssignment))
    ).scalars().all()
    seen = set()
    for a in assignments:
        key = (a.week_id, a.day_index, a.user_id)
        assert key not in seen
        seen.add(key)


@pytest.mark.asyncio
async def test_seed_is_deterministic_and_idempotent(db_session):
    await _guards(db_session)
    r1 = await seed_demo_history(db_session, upcoming_start=UPCOMING, weeks=2, seed=42)
    await db_session.commit()
    r2 = await seed_demo_history(db_session, upcoming_start=UPCOMING, weeks=2, seed=42)
    await db_session.commit()

    assert (r1.assignments, r1.events, r1.kinds) == (r2.assignments, r2.events, r2.kinds)
    # no duplication after the second run — the wipe inside seed cleans first
    events = (await db_session.execute(select(AttendanceEvent))).scalars().all()
    assert len(events) == r2.events


@pytest.mark.asyncio
async def test_wipe_removes_only_demo_data(db_session):
    guards = await _guards(db_session)
    week, real_event = await _real_week_with_data(db_session, guards[0])
    await seed_demo_history(db_session, upcoming_start=UPCOMING, weeks=2, seed=42)
    await db_session.commit()

    result = await wipe_demo(db_session)
    await db_session.commit()

    assert result["profiles_deleted"] == 2
    # demo events gone; the real punch survives
    remaining = (await db_session.execute(select(AttendanceEvent))).scalars().all()
    assert [e.id for e in remaining] == [real_event.id]
    # demo profiles + their positions and assignments cascaded away
    assert (
        await db_session.execute(
            select(ActivationProfile).where(ActivationProfile.name.like("%(DEMO)%"))
        )
    ).scalars().first() is None
    assert (await db_session.execute(select(ScheduleAssignment))).scalars().first() is None
    # the protected real week is untouched
    await db_session.refresh(week)
    assert week.status == WeekStatus.CLOSED


@pytest.mark.asyncio
async def test_seed_never_touches_the_upcoming_week(db_session):
    guards = await _guards(db_session)
    week, real_event = await _real_week_with_data(db_session, guards[0])
    await seed_demo_history(db_session, upcoming_start=UPCOMING, weeks=3, seed=1)
    await db_session.commit()

    # no assignment/punch lands inside the protected week
    assignments = (
        await db_session.execute(select(ScheduleAssignment))
    ).scalars().all()
    week_ids = {a.week_id for a in assignments}
    assert week.id not in week_ids
    # Every demo punch belongs to a day before the boundary — except a
    # night-shift OUT that may land on the boundary MORNING; never later.
    demo_events = (
        await db_session.execute(
            select(AttendanceEvent).where(AttendanceEvent.note == DEMO_NOTE)
        )
    ).scalars().all()
    for e in demo_events:
        assert e.punched_at < datetime(2026, 7, 5, 12, 0)


@pytest.mark.asyncio
async def test_run_refuses_outside_dev(monkeypatch):
    from app.attendance.dev_seed import run
    from app.config import get_settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEV_AUTH_BYPASS_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit):
            await run()
    finally:
        get_settings.cache_clear()
