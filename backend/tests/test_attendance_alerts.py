"""
Stage 3 / 02 step 6 — admin alerts: no-show, long shift, short rest.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.attendance.constants import PunchDirection, PunchSource, ShiftPairStatus
from app.attendance.repositories.adjustment_repository import (
    AttendanceAdjustmentRepository,
)
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.alert_service import AlertService
from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.services.comparison_service import ComparisonService
from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.user_repository import UserRepository
from tests.test_attendance_comparison import StubExport, _planned

D = date(2026, 7, 5)


def _config(**overrides) -> AttendanceConfig:
    base = dict(
        grace_minutes=15, big_gap_minutes=60, site_lat=None, site_lng=None,
        site_radius_m=150, admin_alerts_enabled=True, admin_chat_id="12345",
        company_name="ספרא", long_shift_hours=12, min_rest_hours=8,
    )
    base.update(overrides)
    return AttendanceConfig(**base)


async def _guard(db_session, phone="0501234567", name="יוסי") -> User:
    user = User(phone_number=phone, first_name=name, last_name="כהן", roles=[])
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _week(db_session):
    week = ScheduleWeek(start_date=D, end_date=D + timedelta(days=6), status=WeekStatus.LOCKED)
    db_session.add(week)
    await db_session.commit()


async def _mk_shift(db_session, guard, in_at, out_at, status, work_date):
    events = AttendanceEventRepository(db_session)
    in_ev = await events.add(
        user_id=guard.id, direction=PunchDirection.IN, punched_at=in_at,
        source=PunchSource.TELEGRAM,
    )
    out_ev = None
    if out_at is not None:
        out_ev = await events.add(
            user_id=guard.id, direction=PunchDirection.OUT, punched_at=out_at,
            source=PunchSource.TELEGRAM,
        )
    await AttendanceShiftRepository(db_session).create(
        user_id=guard.id, work_date=work_date, check_in_at=in_at,
        check_out_at=out_at, in_event_id=in_ev.id,
        out_event_id=out_ev.id if out_ev else None, status=status,
        recomputed_at=in_at,
    )
    await db_session.commit()


def _alert_service(db_session, by_guard, config=None, send=None):
    cfg = config or _config()
    comparison = ComparisonService(
        weeks=ScheduleWeekRepository(db_session),
        users=UserRepository(db_session),
        shifts=AttendanceShiftRepository(db_session),
        events=AttendanceEventRepository(db_session),
        export=StubExport(by_guard),
        config=cfg,
        adjustments=AttendanceAdjustmentRepository(db_session),
    )
    sender = send or AsyncMock()
    return AlertService(
        comparison=comparison,
        shifts=AttendanceShiftRepository(db_session),
        config=cfg,
        session=db_session,
        send=sender,
    ), sender


@pytest.mark.asyncio
async def test_no_show_alert_once(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    svc, send = _alert_service(db_session, [_planned(guard)])
    now = datetime(2026, 7, 5, 8, 0)  # 07:00 shift, 45 min past grace

    assert await svc.run_checks(now=now) == 1
    text = send.await_args.args[1]
    assert "🔴" in text and "לא החתים כניסה" in text and "שער ראשי" in text

    # second run — same incident, no re-alert
    assert await svc.run_checks(now=now + timedelta(minutes=10)) == 0


@pytest.mark.asyncio
async def test_no_show_respects_grace_and_toggle(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    svc, send = _alert_service(db_session, [_planned(guard)])
    # only 10 minutes after start — inside grace
    assert await svc.run_checks(now=datetime(2026, 7, 5, 7, 10)) == 0

    off, send_off = _alert_service(
        db_session, [_planned(guard)], config=_config(admin_alerts_enabled=False)
    )
    assert await off.run_checks(now=datetime(2026, 7, 5, 9, 0)) == 0
    send_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_shift_alerts_open_and_complete(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    # open shift since 07:00; now 20:00 → 13h on site
    await _mk_shift(db_session, guard, datetime(2026, 7, 5, 7, 0), None,
                    ShiftPairStatus.OPEN, D)
    svc, send = _alert_service(db_session, [])
    assert await svc.run_checks(now=datetime(2026, 7, 5, 20, 0)) == 1
    assert "🟠" in send.await_args.args[1]
    assert "עדיין לא החתים יציאה" in send.await_args.args[1]

    # 11h open shift → no alert; threshold 0 → check off entirely
    guard2 = await _guard(db_session, phone="0507654321", name="דני")
    await _mk_shift(db_session, guard2, datetime(2026, 7, 5, 7, 0), None,
                    ShiftPairStatus.OPEN, D)
    svc2, send2 = _alert_service(db_session, [], config=_config(long_shift_hours=0))
    assert await svc2.run_checks(now=datetime(2026, 7, 5, 20, 0)) == 0


@pytest.mark.asyncio
async def test_short_rest_alert(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    # out 23:00, back in 04:30 next day → 5.5h rest
    await _mk_shift(db_session, guard, datetime(2026, 7, 4, 15, 0),
                    datetime(2026, 7, 4, 23, 0), ShiftPairStatus.COMPLETE,
                    date(2026, 7, 4))
    await _mk_shift(db_session, guard, datetime(2026, 7, 5, 4, 30), None,
                    ShiftPairStatus.OPEN, D)
    svc, send = _alert_service(db_session, [])
    sent = await svc.run_checks(now=datetime(2026, 7, 5, 6, 0))

    texts = [c.args[1] for c in send.await_args_list]
    rest_alerts = [t for t in texts if "🟡" in t]
    assert len(rest_alerts) == 1
    assert "5:30" in rest_alerts[0]
    # re-run: nothing new
    send.reset_mock()
    await svc.run_checks(now=datetime(2026, 7, 5, 6, 10))
    assert not [c for c in send.await_args_list if "🟡" in c.args[1]]


@pytest.mark.asyncio
async def test_short_rest_skips_missing_out_and_long_rest(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    # previous shift has no out → nothing to measure
    await _mk_shift(db_session, guard, datetime(2026, 7, 4, 15, 0), None,
                    ShiftPairStatus.MISSING_OUT, date(2026, 7, 4))
    await _mk_shift(db_session, guard, datetime(2026, 7, 5, 7, 0), None,
                    ShiftPairStatus.OPEN, D)
    svc, send = _alert_service(db_session, [])
    await svc.run_checks(now=datetime(2026, 7, 5, 8, 0))
    assert not [c for c in send.await_args_list if "🟡" in c.args[1]]


@pytest.mark.asyncio
async def test_send_failure_does_not_kill_the_run(db_session):
    guard = await _guard(db_session)
    await _week(db_session)
    failing = AsyncMock(side_effect=RuntimeError("telegram down"))
    svc, _ = _alert_service(db_session, [_planned(guard)], send=failing)
    # no exception; zero "sent"
    assert await svc.run_checks(now=datetime(2026, 7, 5, 9, 0)) == 0
