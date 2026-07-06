"""
Stage 3 / 02 step 1 — the comparison engine: rounding, interval math,
per-minute classification, tags/severity, day-all and period feeds.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.attendance.constants import PunchDirection, PunchSource, ShiftPairStatus
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.services.comparison_service import (
    KIND_COVERED,
    KIND_EXTRA,
    KIND_FUTURE,
    KIND_GAP_BIG,
    KIND_GAP_SMALL,
    KIND_NO_SHOW,
    ComparisonService,
)
from app.attendance.utils import dt_intervals as di
from app.attendance.utils.rounding import round_out_up_quarter
from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.services.schedule_export_service import (
    GuardSchedule,
    GuardShift,
    WeekSchedule,
)

D = date(2026, 7, 5)  # Sunday — first day of the test week
END_OF_DAY = datetime(2026, 7, 5, 23, 59)


def _config() -> AttendanceConfig:
    return AttendanceConfig(
        grace_minutes=15,
        big_gap_minutes=60,
        site_lat=None,
        site_lng=None,
        site_radius_m=150,
        admin_alerts_enabled=False,
        admin_chat_id="",
        company_name="ספרא",
    )


class StubExport:
    """ScheduleExportService stand-in returning a fixed by_guard cut."""

    def __init__(self, by_guard):
        self._by_guard = by_guard
        self.calls = 0

    async def get_week_schedule(self, week_id):
        self.calls += 1
        return WeekSchedule(week=None, days=[], by_position=[], by_guard=self._by_guard)


async def _guard(db_session, phone="0501234567", name="יוסי") -> User:
    user = User(phone_number=phone, first_name=name, last_name="כהן", roles=[])
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _week(db_session, start=D) -> ScheduleWeek:
    week = ScheduleWeek(
        start_date=start,
        end_date=start + timedelta(days=6),
        status=WeekStatus.LOCKED,
    )
    db_session.add(week)
    await db_session.commit()
    return week


def _planned(guard, day=D, start="07:00", end="15:00", position="שער ראשי"):
    return GuardSchedule(
        user_id=guard.id,
        user_name=guard.full_name,
        telegram_id=None,
        shifts=[
            GuardShift(
                day_index=0,
                date=day.isoformat(),
                position_id=uuid.uuid4(),
                position_name=position,
                start=start,
                end=end,
            )
        ],
    )


async def _mk_shift(
    db_session,
    guard,
    in_at: datetime,
    out_at: datetime | None,
    status: ShiftPairStatus,
    work_date: date = D,
    out_of_radius: bool = False,
):
    events = AttendanceEventRepository(db_session)
    in_ev = await events.add(
        user_id=guard.id,
        direction=PunchDirection.IN,
        punched_at=in_at,
        source=PunchSource.TELEGRAM,
        out_of_radius=out_of_radius or None,
    )
    out_ev = None
    if out_at is not None:
        out_ev = await events.add(
            user_id=guard.id,
            direction=PunchDirection.OUT,
            punched_at=out_at,
            source=PunchSource.TELEGRAM,
        )
    shift = await AttendanceShiftRepository(db_session).create(
        user_id=guard.id,
        work_date=work_date,
        check_in_at=in_at,
        check_out_at=out_at,
        in_event_id=in_ev.id,
        out_event_id=out_ev.id if out_ev else None,
        status=status,
        recomputed_at=in_at,
    )
    await db_session.commit()
    return shift


def _service(db_session, by_guard) -> ComparisonService:
    return ComparisonService(
        weeks=ScheduleWeekRepository(db_session),
        users=UserRepository(db_session),
        shifts=AttendanceShiftRepository(db_session),
        events=AttendanceEventRepository(db_session),
        export=StubExport(by_guard),
        config=_config(),
    )


def _kinds(cmp):
    return {s.kind for s in cmp.segments}


# ---------- rounding ----------

def test_round_out_up_quarter():
    d = datetime(2026, 7, 5, 14, 0)
    assert round_out_up_quarter(d.replace(minute=1)) == d.replace(minute=15)
    assert round_out_up_quarter(d.replace(minute=16)) == d.replace(minute=30)
    assert round_out_up_quarter(d.replace(minute=31)) == d.replace(minute=45)
    assert round_out_up_quarter(d.replace(minute=46)) == datetime(2026, 7, 5, 15, 0)
    # exact quarter stays; stray seconds push up
    assert round_out_up_quarter(d.replace(minute=45)) == d.replace(minute=45)
    assert round_out_up_quarter(d.replace(minute=45, second=1)) == datetime(
        2026, 7, 5, 15, 0
    )


# ---------- dt interval math ----------

def test_dt_interval_math():
    t = lambda h, m=0: datetime(2026, 7, 5, h, m)
    assert di.merge([(t(9), t(11)), (t(10), t(12))]) == [(t(9), t(12))]
    assert di.intersect([(t(7), t(15))], [(t(9), t(10))]) == [(t(9), t(10))]
    assert di.subtract([(t(7), t(15))], [(t(9), t(10))]) == [
        (t(7), t(9)),
        (t(10), t(15)),
    ]
    assert di.total_minutes([(t(7), t(8)), (t(7, 30), t(9))]) == 120


# ---------- classification scenarios ----------

@pytest.mark.asyncio
async def test_exact_coverage_is_ok_and_totals_use_rounded_out(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 7, 2), datetime(2026, 7, 5, 15, 1),
        ShiftPairStatus.COMPLETE,
    )
    svc = _service(db_session, [_planned(guard)])
    cmp = await svc.get_user_day(guard.id, D, now=END_OF_DAY)

    assert cmp.summary.severity == "ok"
    assert "תקין" in cmp.summary.tag
    assert KIND_GAP_SMALL not in _kinds(cmp) and KIND_GAP_BIG not in _kinds(cmp)
    # rounded out 15:01 → 15:15; totals from rounded: 07:02→15:15 = 493
    assert cmp.actual[0].check_out_rounded == datetime(2026, 7, 5, 15, 15)
    assert cmp.summary.actual_minutes == 493
    assert cmp.summary.planned_minutes == 480


@pytest.mark.asyncio
async def test_late_arrival_small_gap(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 7, 25), datetime(2026, 7, 5, 15, 0),
        ShiftPairStatus.COMPLETE,
    )
    svc = _service(db_session, [_planned(guard)])
    cmp = await svc.get_user_day(guard.id, D, now=END_OF_DAY)

    assert cmp.summary.severity == "small"
    assert cmp.summary.tag == "איחור 25 ד'"
    assert cmp.summary.delta_in_minutes == 25
    assert KIND_GAP_SMALL in _kinds(cmp)


@pytest.mark.asyncio
async def test_within_grace_is_clean(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 7, 10), datetime(2026, 7, 5, 15, 0),
        ShiftPairStatus.COMPLETE,
    )
    svc = _service(db_session, [_planned(guard)])
    cmp = await svc.get_user_day(guard.id, D, now=END_OF_DAY)

    assert cmp.summary.severity == "ok"
    assert KIND_GAP_SMALL not in _kinds(cmp)


@pytest.mark.asyncio
async def test_no_show(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    svc = _service(db_session, [_planned(guard)])
    cmp = await svc.get_user_day(guard.id, D, now=END_OF_DAY)

    assert cmp.summary.severity == "big"
    assert cmp.summary.tag == "לא הגיע"
    assert _kinds(cmp) == {KIND_NO_SHOW}


@pytest.mark.asyncio
async def test_future_is_not_a_gap(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    svc = _service(db_session, [_planned(guard)])
    # 06:00 — the whole plan is still ahead
    cmp = await svc.get_user_day(guard.id, D, now=datetime(2026, 7, 5, 6, 0))

    assert _kinds(cmp) == {KIND_FUTURE}
    assert cmp.summary.severity == "none"
    assert cmp.summary.tag == "טרם התחיל"


@pytest.mark.asyncio
async def test_mid_shift_now_clips_classification(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard, datetime(2026, 7, 5, 7, 0), None, ShiftPairStatus.OPEN
    )
    svc = _service(db_session, [_planned(guard)])
    cmp = await svc.get_user_day(guard.id, D, now=datetime(2026, 7, 5, 11, 0))

    assert cmp.summary.severity == "ok"
    assert cmp.summary.tag == "בעמדה ✔"
    kinds = _kinds(cmp)
    assert KIND_COVERED in kinds and KIND_FUTURE in kinds
    assert KIND_GAP_SMALL not in kinds and KIND_GAP_BIG not in kinds


@pytest.mark.asyncio
async def test_missing_out_is_big_and_counts_zero(db_session):
    """Option 1 (4/7): a shift with no verified out contributes NOTHING to the
    totals and covers nothing on the timeline until the admin completes it."""
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard, datetime(2026, 7, 5, 7, 0), None,
        ShiftPairStatus.MISSING_OUT,
    )
    svc = _service(db_session, [_planned(guard)])
    cmp = await svc.get_user_day(guard.id, D, now=datetime(2026, 7, 6, 12, 0))

    assert cmp.summary.severity == "big"
    assert cmp.summary.tag == "אין יציאה"
    assert cmp.summary.actual_minutes == 0          # no phantom 16h
    assert KIND_COVERED not in _kinds(cmp)          # nothing verified = nothing covered
    assert KIND_GAP_BIG in _kinds(cmp)              # the plan shows as uncovered


@pytest.mark.asyncio
async def test_unscheduled_presence(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 8, 0), datetime(2026, 7, 5, 12, 47),
        ShiftPairStatus.COMPLETE,
    )
    svc = _service(db_session, [])  # not on the schedule at all
    cmp = await svc.get_user_day(guard.id, D, now=END_OF_DAY)

    assert cmp.summary.severity == "small"
    assert cmp.summary.tag == "ללא שיבוץ"
    assert _kinds(cmp) == {KIND_EXTRA}


@pytest.mark.asyncio
async def test_orphan_out_flagged(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await AttendanceEventRepository(db_session).add(
        user_id=guard.id,
        direction=PunchDirection.OUT,
        punched_at=datetime(2026, 7, 5, 15, 0),
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()
    svc = _service(db_session, [])
    cmp = await svc.get_user_day(guard.id, D, now=END_OF_DAY)

    assert cmp.summary.orphan_out_times == ["15:00"]
    assert cmp.summary.severity == "big"
    assert cmp.summary.tag == "יציאה בלי כניסה"
    # The orphan is exposed with its raw event id so the edit dialog can
    # list/fix/void it like any paired punch.
    assert len(cmp.summary.orphan_outs) == 1
    orphan = cmp.summary.orphan_outs[0]
    assert orphan.event_id is not None
    assert orphan.punched_at == datetime(2026, 7, 5, 15, 0)
    assert orphan.source == PunchSource.TELEGRAM.value


@pytest.mark.asyncio
async def test_night_shift_geometry(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 22, 54), datetime(2026, 7, 6, 7, 3),
        ShiftPairStatus.COMPLETE,
    )
    svc = _service(
        db_session, [_planned(guard, start="23:00", end="07:00")]
    )
    cmp = await svc.get_user_day(guard.id, D, now=datetime(2026, 7, 6, 12, 0))

    assert cmp.summary.severity == "ok"
    # planned window crosses midnight into the 6th
    assert cmp.planned[0].end == datetime(2026, 7, 6, 7, 0)
    assert cmp.summary.planned_minutes == 480
    # the 6 early minutes are "extra", the 3 late ones too
    assert KIND_EXTRA in _kinds(cmp)


# ---------- day-all + period ----------

@pytest.mark.asyncio
async def test_day_all_counters_and_sort(db_session):
    present = await _guard(db_session, phone="0501111111", name="נוכח")
    absent = await _guard(db_session, phone="0502222222", name="נעדר")
    await _week(db_session)
    await _mk_shift(
        db_session, present,
        datetime(2026, 7, 5, 7, 0), datetime(2026, 7, 5, 15, 0),
        ShiftPairStatus.COMPLETE,
    )
    svc = _service(
        db_session, [_planned(present), _planned(absent)]
    )
    day = await svc.get_day_all(D, now=END_OF_DAY)

    assert day["counters"] == {"scheduled": 2, "present": 1, "big": 1, "small": 0}
    # the no-show sorts first
    assert day["rows"][0].summary.tag == "לא הגיע"
    assert day["rows"][1].summary.severity == "ok"


@pytest.mark.asyncio
async def test_period_summary_aggregates_and_sorts(db_session):
    present = await _guard(db_session, phone="0501111111", name="נוכח")
    absent = await _guard(db_session, phone="0502222222", name="נעדר")
    await _week(db_session)
    # present: two clean days
    for d in (5, 6):
        await _mk_shift(
            db_session, present,
            datetime(2026, 7, d, 7, 0), datetime(2026, 7, d, 15, 0),
            ShiftPairStatus.COMPLETE, work_date=date(2026, 7, d),
        )
    svc = _service(db_session, [_planned(present), _planned(absent)])
    # both planned only on the 5th (stub), scan 5th–6th
    rows = await svc.get_period_summary(
        D, date(2026, 7, 6), now=datetime(2026, 7, 7, 12, 0)
    )

    by_name = {r["user_name"]: r for r in rows}
    assert by_name["נעדר כהן"]["big"] == 1          # no-show on the 5th
    assert by_name["נוכח כהן"]["days_present"] == 2
    assert by_name["נוכח כהן"]["actual_minutes"] == 960
    # problems sort first
    assert rows[0]["user_name"] == "נעדר כהן"


@pytest.mark.asyncio
async def test_extra_unscheduled_guards_surface_in_day_view(db_session):
    """More guards showed up than the schedule knows: the extra one appears
    with punch hours only (no planned lane) — and even a guard whose ONLY
    record is an orphan OUT is listed, not swallowed."""
    scheduled = await _guard(db_session, phone="0501111111", name="משובץ")
    extra = await _guard(db_session, phone="0502222222", name="עודף")
    orphan = await _guard(db_session, phone="0503333333", name="יתום")
    await _week(db_session)

    await _mk_shift(
        db_session, scheduled,
        datetime(2026, 7, 5, 7, 0), datetime(2026, 7, 5, 15, 0),
        ShiftPairStatus.COMPLETE,
    )
    # the extra guard punched a full unscheduled shift
    await _mk_shift(
        db_session, extra,
        datetime(2026, 7, 5, 9, 0), datetime(2026, 7, 5, 13, 0),
        ShiftPairStatus.COMPLETE,
    )
    # the orphan guard has ONE lone OUT punch — no shift derives from it
    await AttendanceEventRepository(db_session).add(
        user_id=orphan.id,
        direction=PunchDirection.OUT,
        punched_at=datetime(2026, 7, 5, 14, 0),
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()

    svc = _service(db_session, [_planned(scheduled)])
    day = await svc.get_day_all(D, now=END_OF_DAY)

    by_name = {r.user_name: r for r in day["rows"]}
    assert set(by_name) == {"משובץ כהן", "עודף כהן", "יתום כהן"}
    assert by_name["עודף כהן"].planned == []
    assert by_name["עודף כהן"].summary.tag == "ללא שיבוץ"
    assert by_name["עודף כהן"].actual[0].check_in_at == datetime(2026, 7, 5, 9, 0)
    assert by_name["יתום כהן"].summary.tag == "יציאה בלי כניסה"
    assert by_name["יתום כהן"].summary.orphan_out_times == ["14:00"]


@pytest.mark.asyncio
async def test_inactive_guard_who_punched_keeps_their_name(db_session):
    ghost = await _guard(db_session, phone="0504444444", name="מושבת")
    ghost.is_active = False
    await db_session.commit()
    await _week(db_session)
    await _mk_shift(
        db_session, ghost,
        datetime(2026, 7, 5, 8, 0), datetime(2026, 7, 5, 12, 0),
        ShiftPairStatus.COMPLETE,
    )
    svc = _service(db_session, [])
    day = await svc.get_day_all(D, now=END_OF_DAY)
    assert day["rows"][0].user_name == "מושבת כהן"


@pytest.mark.asyncio
async def test_user_period_includes_orphan_only_day(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await AttendanceEventRepository(db_session).add(
        user_id=guard.id,
        direction=PunchDirection.OUT,
        punched_at=datetime(2026, 7, 6, 15, 0),
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()
    svc = _service(db_session, [])
    period = await svc.get_user_period(
        guard.id, D, date(2026, 7, 8), now=datetime(2026, 7, 9, 12, 0)
    )
    assert [d.date for d in period["days"]] == [date(2026, 7, 6)]
    assert period["days"][0].summary.tag == "יציאה בלי כניסה"


@pytest.mark.asyncio
async def test_user_period_includes_only_relevant_days(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 6, 7, 0), datetime(2026, 7, 6, 15, 2),
        ShiftPairStatus.COMPLETE,
        work_date=date(2026, 7, 6),
    )
    # planned only on the 5th; punched only on the 6th; nothing on the 7th
    svc = _service(db_session, [_planned(guard)])
    period = await svc.get_user_period(
        guard.id, D, date(2026, 7, 8), now=datetime(2026, 7, 9, 12, 0)
    )

    assert [d.date for d in period["days"]] == [D, date(2026, 7, 6)]
    assert period["days"][0].summary.tag == "לא הגיע"
    assert period["days"][1].summary.tag == "ללא שיבוץ"
    # totals: 07:00→15:15 (rounded) = 495
    assert period["summary"]["actual_minutes"] == 495
    assert period["summary"]["big"] == 1 and period["summary"]["small"] == 1
