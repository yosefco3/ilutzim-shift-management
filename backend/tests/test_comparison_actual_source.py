"""
Step 04 — the attendance comparison reads the ACTUAL schedule behind
``ACTUAL_SCHEDULE_ENABLED``.

The scenario that motivated the whole feature: guard A was planned, guard B
actually showed up (day-of replacement). With the flag ON and the actual board
edited (A→B), the comparison must treat B as the scheduled guard; with the flag
OFF it keeps the pre-feature reading (A no-show, B unscheduled extra).
"""

from datetime import datetime, time, timedelta

import pytest

import app.attendance.dependencies as attendance_deps
from app.attendance.constants import ShiftPairStatus
from app.attendance.dependencies import build_comparison_service
from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment
from app.schedule_builder.repositories.actual_schedule_repository import (
    ActualScheduleRepository,
)
from app.utils.date_utils import today_il

from tests.test_attendance_comparison import _mk_shift  # reuse the punch helper


class _FlagStub:
    def __init__(self, enabled: bool):
        self.ACTUAL_SCHEDULE_ENABLED = enabled


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(
        attendance_deps, "get_settings", lambda: _FlagStub(True)
    )


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(
        attendance_deps, "get_settings", lambda: _FlagStub(False)
    )


async def _replacement_scenario(db_session):
    """A finished week: guard A planned on day 0, guard B actually punched."""
    start = today_il() - timedelta(days=today_il().weekday() + 8)  # past week
    week = ScheduleWeek(
        start_date=start, end_date=start + timedelta(days=6),
        status=WeekStatus.LOCKED,
    )
    db_session.add(week)
    await db_session.flush()

    profile = ActivationProfile(name="שגרה", is_default=True)
    db_session.add(profile)
    await db_session.flush()
    db_session.add(WeekProfileAssignment(week_id=week.id, profile_id=profile.id))
    position = Position(
        profile_id=profile.id, name="שער ראשי",
        day_schedules={"0": {"start": "07:00", "end": "15:00"}},
    )
    db_session.add(position)
    await db_session.flush()

    guard_a = User(phone_number="0501111111", first_name="אלף", last_name="מתוכנן")
    guard_b = User(phone_number="0502222222", first_name="בית", last_name="מחליף")
    db_session.add_all([guard_a, guard_b])
    await db_session.flush()

    db_session.add(ScheduleAssignment(
        week_id=week.id, position_id=position.id, day_index=0, user_id=guard_a.id,
    ))
    await db_session.commit()

    # Guard B punched a clean 07:00–15:00 on day 0.
    day0 = week.start_date
    await _mk_shift(
        db_session, guard_b,
        in_at=datetime.combine(day0, time(7, 0)),
        out_at=datetime.combine(day0, time(15, 0)),
        status=ShiftPairStatus.COMPLETE,
        work_date=day0,
    )
    return week, position, guard_a, guard_b


async def _swap_actual_to_b(db_session, week, guard_a, guard_b):
    """Seed the actual copy and apply the day-of edit: A → B."""
    from app.schedule_builder.dependencies import build_actual_schedule_service

    actual = await build_actual_schedule_service(db_session).ensure_for_week(week.id)
    repo = ActualScheduleRepository(db_session)
    (assignment,) = await repo.list_assignments(actual.id)
    assert assignment.user_id == guard_a.id
    assignment.user_id = guard_b.id
    await db_session.commit()


def _row(day_all, user) -> object | None:
    return next((r for r in day_all["rows"] if r.user_id == user.id), None)


@pytest.mark.asyncio
async def test_flag_on_comparison_follows_the_actual_edit(db_session, flag_on):
    week, _, guard_a, guard_b = await _replacement_scenario(db_session)
    await _swap_actual_to_b(db_session, week, guard_a, guard_b)

    comparison = await build_comparison_service(db_session)
    now = datetime.combine(week.end_date + timedelta(days=1), time(12, 0))
    day_all = await comparison.get_day_all(week.start_date, now=now)

    b_row = _row(day_all, guard_b)
    assert b_row is not None and b_row.planned, "B must be the scheduled guard"
    assert b_row.summary.severity == "ok"
    assert b_row.summary.planned_minutes == 8 * 60
    assert b_row.summary.actual_minutes == 8 * 60

    a_row = _row(day_all, guard_a)
    assert a_row is None, "A is no longer scheduled and never punched"


@pytest.mark.asyncio
async def test_flag_off_keeps_the_pre_feature_reading(db_session, flag_off):
    week, _, guard_a, guard_b = await _replacement_scenario(db_session)
    await _swap_actual_to_b(db_session, week, guard_a, guard_b)

    comparison = await build_comparison_service(db_session)
    now = datetime.combine(week.end_date + timedelta(days=1), time(12, 0))
    day_all = await comparison.get_day_all(week.start_date, now=now)

    a_row = _row(day_all, guard_a)
    assert a_row is not None and a_row.planned, "flag off → plan still rules"
    assert a_row.summary.actual_minutes == 0  # no-show

    b_row = _row(day_all, guard_b)
    assert b_row is not None
    assert not b_row.planned  # unscheduled extra
    assert b_row.summary.actual_minutes == 8 * 60


@pytest.mark.asyncio
async def test_flag_on_payroll_norm_follows_the_actual(db_session, flag_on):
    """The payroll read model (norm minutes) inherits the actual source."""
    from app.attendance.services.payroll_readmodel import PayrollReadModel
    from app.repositories.user_repository import UserRepository

    week, _, guard_a, guard_b = await _replacement_scenario(db_session)
    await _swap_actual_to_b(db_session, week, guard_a, guard_b)

    comparison = await build_comparison_service(db_session)
    payroll = PayrollReadModel(
        comparison, UserRepository(db_session), comparison.config
    )
    day0 = week.start_date
    month = await payroll.get_month(
        guard_b.id, day0.year, day0.month,
        now=datetime.combine(week.end_date + timedelta(days=1), time(12, 0)),
    )
    day_rows = [r for r in month.rows if r.day == day0]
    assert day_rows and day_rows[0].norm_minutes == 8 * 60
    assert day_rows[0].site == "שער ראשי"
