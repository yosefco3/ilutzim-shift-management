"""
Stage 3 / 03 step 1 — the monthly payroll read-model (feeds both YLM reports).
"""

from datetime import date, datetime, timedelta

import pytest

from app.attendance.constants import PunchDirection, PunchSource, ShiftPairStatus
from app.attendance.repositories.adjustment_repository import (
    AttendanceAdjustmentRepository,
)
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.comparison_service import ComparisonService
from app.attendance.services.payroll_readmodel import (
    PayrollReadModel,
    minutes_hhmm,
)
from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.user_repository import UserRepository
from tests.test_attendance_comparison import StubExport, _config, _planned

D = date(2026, 7, 5)  # Sunday inside July 2026
NOW = datetime(2026, 8, 2, 12, 0)  # safely after the month


async def _guard(db_session, **payroll) -> User:
    user = User(
        phone_number="0501234567", first_name="יוסי", last_name="כהן", roles=[],
        **payroll,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _week(db_session):
    week = ScheduleWeek(
        start_date=D, end_date=D + timedelta(days=6), status=WeekStatus.LOCKED
    )
    db_session.add(week)
    await db_session.commit()


async def _mk_shift(db_session, guard, in_at, out_at, status, work_date,
                    out_source=PunchSource.TELEGRAM):
    events = AttendanceEventRepository(db_session)
    in_ev = await events.add(
        user_id=guard.id, direction=PunchDirection.IN, punched_at=in_at,
        source=PunchSource.TELEGRAM,
    )
    out_ev = None
    if out_at is not None:
        out_ev = await events.add(
            user_id=guard.id, direction=PunchDirection.OUT, punched_at=out_at,
            source=out_source,
        )
    await AttendanceShiftRepository(db_session).create(
        user_id=guard.id, work_date=work_date, check_in_at=in_at,
        check_out_at=out_at, in_event_id=in_ev.id,
        out_event_id=out_ev.id if out_ev else None, status=status,
        recomputed_at=in_at,
    )
    await db_session.commit()


def _readmodel(db_session, by_guard) -> PayrollReadModel:
    comparison = ComparisonService(
        weeks=ScheduleWeekRepository(db_session),
        users=UserRepository(db_session),
        shifts=AttendanceShiftRepository(db_session),
        events=AttendanceEventRepository(db_session),
        export=StubExport(by_guard),
        config=_config(),
        adjustments=AttendanceAdjustmentRepository(db_session),
    )
    return PayrollReadModel(comparison, UserRepository(db_session), _config())


def test_minutes_hhmm_formatting():
    assert minutes_hhmm(0) == "0:00"
    assert minutes_hhmm(493) == "8:13"
    assert minutes_hhmm(-2021) == "-33:41"


@pytest.mark.asyncio
async def test_month_has_a_row_for_every_calendar_day(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    model = _readmodel(db_session, [])
    month = await model.get_month(guard.id, 2026, 7, now=NOW)

    assert len(month.rows) == 31  # empty July, one row per day
    assert month.rows[0].day_letter == "ד"   # 2026-07-01 is a Wednesday
    assert month.rows[4].day_letter == "א"   # the 5th is a Sunday
    assert month.totals.actual_minutes == 0


@pytest.mark.asyncio
async def test_header_and_worked_day_semantics(db_session):
    guard = await _guard(
        db_session,
        payroll_employee_id="605182",
        payroll_ylm_code="605182",
        national_id="034465773",
    )
    await _week(db_session)
    # worked day: in 07:02, out 15:01 → rounded 15:15
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 7, 2), datetime(2026, 7, 5, 15, 1),
        ShiftPairStatus.COMPLETE, D,
    )
    model = _readmodel(db_session, [_planned(guard)])
    month = await model.get_month(guard.id, 2026, 7, now=NOW)

    assert month.payroll_employee_id == "605182"
    assert month.national_id == "034465773"
    assert month.company_name == "ספרא"

    row = next(r for r in month.rows if r.day == D)
    assert row.site == "שער ראשי"
    assert row.check_in == datetime(2026, 7, 5, 7, 2)          # exact
    assert row.check_out == datetime(2026, 7, 5, 15, 15)       # rounded up
    assert "יציאה בפועל 15:01" in row.notes
    assert row.total_minutes == 493
    assert row.norm_minutes == 480
    assert row.diff_minutes == 13
    assert month.totals.work_days == 1
    assert month.totals.diff_minutes == 13


@pytest.mark.asyncio
async def test_no_show_day_and_negative_diff(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    model = _readmodel(db_session, [_planned(guard)])
    month = await model.get_month(guard.id, 2026, 7, now=NOW)

    row = next(r for r in month.rows if r.day == D)
    assert row.site == "שער ראשי"
    assert row.check_in is None and row.check_out is None
    assert row.norm_minutes == 480
    assert row.diff_minutes == -480
    assert month.totals.diff_minutes == -480
    assert minutes_hhmm(month.totals.diff_minutes) == "-8:00"


@pytest.mark.asyncio
async def test_admin_entered_out_is_final_not_rounded(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 7, 0), datetime(2026, 7, 5, 15, 1),
        ShiftPairStatus.COMPLETE, D,
        out_source=PunchSource.MANUAL,
    )
    model = _readmodel(db_session, [_planned(guard)])
    month = await model.get_month(guard.id, 2026, 7, now=NOW)

    row = next(r for r in month.rows if r.day == D)
    assert row.check_out == datetime(2026, 7, 5, 15, 1)  # exactly as typed
    assert row.edited is True
    assert "הוזן/תוקן ידנית" in row.notes


@pytest.mark.asyncio
async def test_two_shifts_day_prints_two_rows_norm_once(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 7, 0), datetime(2026, 7, 5, 11, 0),
        ShiftPairStatus.COMPLETE, D,
    )
    await _mk_shift(
        db_session, guard,
        datetime(2026, 7, 5, 15, 0), datetime(2026, 7, 5, 19, 0),
        ShiftPairStatus.COMPLETE, D,
    )
    model = _readmodel(db_session, [_planned(guard)])
    month = await model.get_month(guard.id, 2026, 7, now=NOW)

    day_rows = [r for r in month.rows if r.day == D]
    assert len(day_rows) == 2
    assert day_rows[0].norm_minutes == 480 and day_rows[1].norm_minutes is None
    assert day_rows[1].diff_minutes is None


@pytest.mark.asyncio
async def test_month_all_sorted_and_active_only(db_session):
    b = await _guard(db_session)
    a = User(phone_number="0507654321", first_name="אבי", last_name="אלף", roles=[])
    ghost = User(
        phone_number="0501112233", first_name="רפאים", last_name="לא-פעיל",
        roles=[], is_active=False,
    )
    db_session.add_all([a, ghost])
    await db_session.commit()
    await _week(db_session)

    model = _readmodel(db_session, [])
    months = await model.get_month_all(2026, 7, now=NOW)
    names = [m.user_name for m in months]
    assert names == sorted(names)
    assert "רפאים לא-פעיל" not in names
    assert len(months) == 2
