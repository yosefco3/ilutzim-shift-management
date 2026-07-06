"""
Stage 3 / 02 step 5 — admin corrections: audit rows, effective events,
recompute, absence approval in the comparison.
"""

from datetime import date, datetime

import pytest

from app.attendance.constants import (
    AdjustmentAction,
    PunchDirection,
    PunchSource,
    ShiftPairStatus,
)
from app.attendance.repositories.adjustment_repository import (
    AttendanceAdjustmentRepository,
)
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.adjustment_service import AdjustmentService
from app.attendance.services.pairing_service import PairingService
from app.exceptions import ValidationException
from app.models.user import User

D = date(2026, 7, 5)
NOW = datetime(2026, 7, 7, 12, 0)


async def _guard(db_session) -> User:
    user = User(phone_number="0501234567", first_name="יוסי", last_name="כהן", roles=[])
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _services(db_session):
    events = AttendanceEventRepository(db_session)
    shifts = AttendanceShiftRepository(db_session)
    adjustments = AttendanceAdjustmentRepository(db_session)
    pairing = PairingService(events, shifts)
    return AdjustmentService(events, adjustments, pairing), events, shifts, adjustments


async def _punch(events, db_session, guard, direction, at):
    ev = await events.add(
        user_id=guard.id, direction=direction, punched_at=at,
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()
    return ev


@pytest.mark.asyncio
async def test_edit_time_voids_original_and_reshapes_shift(db_session):
    guard = await _guard(db_session)
    service, events, shifts, adjustments = _services(db_session)
    in_ev = await _punch(events, db_session, guard, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    out_ev = await _punch(events, db_session, guard, PunchDirection.OUT, datetime(2026, 7, 5, 15, 0))
    await service._pairing.recompute_for_punch(guard.id, datetime(2026, 7, 5, 15, 0))
    await db_session.commit()

    # admin fixes the out to 16:30
    adj = await service.edit_time(
        out_ev.id, datetime(2026, 7, 5, 16, 30), "נשאר לתגבור", now=NOW
    )
    await db_session.commit()

    assert adj.action == AdjustmentAction.EDIT_TIME
    assert adj.before["punched_at"].startswith("2026-07-05T15:00")
    rows = await shifts.list_for_user(guard.id, D, D)
    assert len(rows) == 1
    assert rows[0].check_out_at == datetime(2026, 7, 5, 16, 30)
    assert rows[0].status == ShiftPairStatus.COMPLETE
    # the original raw row still exists (audit), but is no longer effective
    assert await events.get_by_id(out_ev.id) is not None
    effective = await events.list_effective_for_user(
        guard.id, datetime(2026, 7, 5), datetime(2026, 7, 6)
    )
    assert out_ev.id not in {e.id for e in effective}
    assert in_ev.id in {e.id for e in effective}


@pytest.mark.asyncio
async def test_add_punch_completes_missing_out(db_session):
    guard = await _guard(db_session)
    service, events, shifts, _ = _services(db_session)
    await _punch(events, db_session, guard, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    await service._pairing.recompute_for_punch(guard.id, datetime(2026, 7, 5, 7, 0))
    await db_session.commit()

    await service.add_punch(
        guard.id, PunchDirection.OUT, datetime(2026, 7, 5, 15, 0),
        "שכח להחתים יציאה", now=NOW,
    )
    await db_session.commit()

    rows = await shifts.list_for_user(guard.id, D, D)
    assert rows[0].status == ShiftPairStatus.COMPLETE
    assert rows[0].check_out_at == datetime(2026, 7, 5, 15, 0)
    # the manual event is marked as such
    out_ev = await events.get_by_id(rows[0].out_event_id)
    assert out_ev.source == PunchSource.MANUAL
    assert out_ev.created_by_admin is True


@pytest.mark.asyncio
async def test_void_punch_removes_derived_shift(db_session):
    guard = await _guard(db_session)
    service, events, shifts, _ = _services(db_session)
    in_ev = await _punch(events, db_session, guard, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    await service._pairing.recompute_for_punch(guard.id, datetime(2026, 7, 5, 7, 0))
    await db_session.commit()
    assert len(await shifts.list_for_user(guard.id, D, D)) == 1

    await service.void_punch(in_ev.id, "החתמה בטעות")
    await db_session.commit()

    assert await shifts.list_for_user(guard.id, D, D) == []
    assert await events.get_by_id(in_ev.id) is not None  # raw survives


@pytest.mark.asyncio
async def test_reason_required_and_no_future_times(db_session):
    guard = await _guard(db_session)
    service, events, _, _ = _services(db_session)
    ev = await _punch(events, db_session, guard, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))

    with pytest.raises(ValidationException):
        await service.void_punch(ev.id, " ")
    with pytest.raises(ValidationException):
        await service.edit_time(ev.id, NOW.replace(hour=23), "סיבה", now=NOW)
    with pytest.raises(ValidationException):
        await service.add_punch(
            guard.id, PunchDirection.IN, NOW.replace(hour=23), "סיבה", now=NOW
        )


@pytest.mark.asyncio
async def test_mark_absence_clears_no_show_in_comparison(db_session):
    from app.attendance.services.attendance_settings import AttendanceConfig
    from app.attendance.services.comparison_service import (
        KIND_NO_SHOW,
        ComparisonService,
    )
    from app.constants import WeekStatus
    from app.models.schedule_week import ScheduleWeek
    from app.repositories.schedule_week_repository import ScheduleWeekRepository
    from app.repositories.user_repository import UserRepository
    from tests.test_attendance_comparison import StubExport, _planned

    guard = await _guard(db_session)
    week = ScheduleWeek(start_date=D, end_date=date(2026, 7, 11), status=WeekStatus.LOCKED)
    db_session.add(week)
    await db_session.commit()

    service, _, _, adjustments = _services(db_session)
    config = AttendanceConfig(
        grace_minutes=15, big_gap_minutes=60, site_lat=None, site_lng=None,
        site_radius_m=150, admin_alerts_enabled=False, admin_chat_id="",
        company_name="ספרא",
    )
    comparison = ComparisonService(
        weeks=ScheduleWeekRepository(db_session),
        users=UserRepository(db_session),
        shifts=AttendanceShiftRepository(db_session),
        events=AttendanceEventRepository(db_session),
        export=StubExport([_planned(guard)]),
        config=config,
        adjustments=adjustments,
    )

    before = await comparison.get_user_day(guard.id, D, now=NOW)
    assert before.summary.tag == "לא הגיע"

    await service.mark_absence(guard.id, D, "מחלה מאושרת")
    await db_session.commit()

    after = await comparison.get_user_day(guard.id, D, now=NOW)
    assert after.summary.severity == "ok"
    assert after.summary.tag == "היעדרות מאושרת ✎"
    assert KIND_NO_SHOW not in {s.kind for s in after.segments}


@pytest.mark.asyncio
async def test_manual_entry_full_day_and_night_crossing(db_session):
    """Two add_punch calls (the manual-entry endpoint's core) create a
    COMPLETE manual shift; a night out ≤ in crosses midnight."""
    guard = await _guard(db_session)
    service, events, shifts, _ = _services(db_session)

    # regular day 07:00–15:00
    await service.add_punch(guard.id, PunchDirection.IN, datetime(2026, 7, 5, 7, 0), "עובד ללא טלגרם", now=NOW)
    await service.add_punch(guard.id, PunchDirection.OUT, datetime(2026, 7, 5, 15, 0), "עובד ללא טלגרם", now=NOW)
    await db_session.commit()
    rows = await shifts.list_for_user(guard.id, D, D)
    assert rows[0].status == ShiftPairStatus.COMPLETE
    in_ev = await events.get_by_id(rows[0].in_event_id)
    assert in_ev.source == PunchSource.MANUAL

    # night guard: in 23:00 on the 6th, out 07:00 "on the 6th" → the 7th
    d6 = date(2026, 7, 6)
    await service.add_punch(guard.id, PunchDirection.IN, datetime(2026, 7, 6, 23, 0), "לילה", now=NOW)
    await service.add_punch(guard.id, PunchDirection.OUT, datetime(2026, 7, 7, 7, 0), "לילה", now=datetime(2026, 7, 8, 12, 0))
    await db_session.commit()
    night = await shifts.list_for_user(guard.id, d6, d6)
    assert night[0].status == ShiftPairStatus.COMPLETE
    assert night[0].work_date == d6
    assert night[0].check_out_at == datetime(2026, 7, 7, 7, 0)


@pytest.mark.asyncio
async def test_history_returns_the_trail(db_session):
    guard = await _guard(db_session)
    service, events, _, _ = _services(db_session)
    ev = await _punch(events, db_session, guard, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    await service.void_punch(ev.id, "בטעות")
    await service.mark_absence(guard.id, D, "מחלה")
    await db_session.commit()

    trail = await service.history(guard.id, D)
    assert [a.action for a in trail] == [
        AdjustmentAction.VOID_PUNCH,
        AdjustmentAction.MARK_ABSENCE,
    ]

    # the trail itself is append-only
    repo = AttendanceAdjustmentRepository(db_session)
    with pytest.raises(RuntimeError):
        await repo.delete(trail[0].id)
