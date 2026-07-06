"""
Stage 3 / 01 step 5 — the IN/OUT pairing engine (the delicate part).
"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.attendance.constants import PunchDirection, PunchSource, ShiftPairStatus
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.pairing_service import PairingService
from app.models.user import User

D = date(2026, 7, 5)  # a Sunday
NOW = datetime(2026, 7, 7, 12, 0)  # "now" safely after the tested days


async def _guard(db_session, phone="0501234567") -> User:
    user = User(phone_number=phone, first_name="יוסי", last_name="כהן", roles=[])
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _svc(db_session) -> PairingService:
    return PairingService(
        AttendanceEventRepository(db_session),
        AttendanceShiftRepository(db_session),
    )


async def _punch(db_session, user, direction, at: datetime):
    await AttendanceEventRepository(db_session).add(
        user_id=user.id,
        direction=direction,
        punched_at=at,
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()


async def _shifts(db_session, user, date_from=D - timedelta(days=2), date_to=D + timedelta(days=2)):
    return await AttendanceShiftRepository(db_session).list_for_user(
        user.id, date_from, date_to
    )


@pytest.mark.asyncio
async def test_regular_day(db_session):
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 7, 2))
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 5, 15, 1))

    await _svc(db_session).recompute_user(user.id, D, D, now=NOW)
    shifts = await _shifts(db_session, user)

    assert len(shifts) == 1
    s = shifts[0]
    assert s.status == ShiftPairStatus.COMPLETE
    assert s.work_date == D
    assert s.check_in_at == datetime(2026, 7, 5, 7, 2)
    assert s.check_out_at == datetime(2026, 7, 5, 15, 1)


@pytest.mark.asyncio
async def test_night_shift_crossing_midnight_attributed_to_start_day(db_session):
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 22, 54))
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 6, 7, 3))

    # Recompute triggered by the OUT punch day (the 6th) — the widened window
    # must still find and rebuild the shift that STARTED on the 5th.
    await _svc(db_session).recompute_user(
        user.id, D + timedelta(days=1), D + timedelta(days=1), now=NOW
    )
    shifts = await _shifts(db_session, user)

    assert len(shifts) == 1
    s = shifts[0]
    assert s.status == ShiftPairStatus.COMPLETE
    assert s.work_date == D  # attributed to the day it started
    assert s.check_out_at == datetime(2026, 7, 6, 7, 3)


@pytest.mark.asyncio
async def test_two_shifts_same_day(db_session):
    user = await _guard(db_session)
    for h_in, h_out in [(7, 11), (15, 19)]:
        await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, h_in, 0))
        await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 5, h_out, 0))

    await _svc(db_session).recompute_user(user.id, D, D, now=NOW)
    shifts = await _shifts(db_session, user)

    assert [s.status for s in shifts] == [ShiftPairStatus.COMPLETE] * 2
    assert [s.check_in_at.hour for s in shifts] == [7, 15]


@pytest.mark.asyncio
async def test_in_in_marks_first_missing_out(db_session):
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 15, 0))
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 5, 23, 0))

    await _svc(db_session).recompute_user(user.id, D, D, now=NOW)
    shifts = await _shifts(db_session, user)

    assert len(shifts) == 2
    assert shifts[0].status == ShiftPairStatus.MISSING_OUT
    assert shifts[0].check_out_at is None
    assert shifts[1].status == ShiftPairStatus.COMPLETE


@pytest.mark.asyncio
async def test_orphan_out_is_skipped(db_session):
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 5, 15, 0))

    await _svc(db_session).recompute_user(user.id, D, D, now=NOW)
    assert await _shifts(db_session, user) == []


@pytest.mark.asyncio
async def test_out_beyond_ceiling_does_not_close(db_session):
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    # 20h later — beyond the 16h ceiling
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 6, 3, 0) + timedelta(hours=8))

    await _svc(db_session).recompute_user(user.id, D, D, now=NOW)
    shifts = await _shifts(db_session, user)

    assert len(shifts) == 1
    assert shifts[0].status == ShiftPairStatus.MISSING_OUT
    assert shifts[0].check_out_at is None


@pytest.mark.asyncio
async def test_trailing_in_open_vs_missing_out(db_session):
    user = await _guard(db_session)
    check_in = datetime(2026, 7, 5, 7, 0)
    await _punch(db_session, user, PunchDirection.IN, check_in)

    svc = _svc(db_session)

    # 3 hours in → still plausibly on shift
    await svc.recompute_user(user.id, D, D, now=check_in + timedelta(hours=3))
    shifts = await _shifts(db_session, user)
    assert shifts[0].status == ShiftPairStatus.OPEN

    # 20 hours in → clearly forgot to punch out
    await svc.recompute_user(user.id, D, D, now=check_in + timedelta(hours=20))
    shifts = await _shifts(db_session, user)
    assert shifts[0].status == ShiftPairStatus.MISSING_OUT


@pytest.mark.asyncio
async def test_recompute_is_idempotent(db_session):
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 5, 15, 0))

    svc = _svc(db_session)
    await svc.recompute_user(user.id, D, D, now=NOW)
    first = [(s.check_in_at, s.check_out_at, s.status) for s in await _shifts(db_session, user)]

    await svc.recompute_user(user.id, D, D, now=NOW)
    await svc.recompute_user(user.id, D, D, now=NOW)
    again = [(s.check_in_at, s.check_out_at, s.status) for s in await _shifts(db_session, user)]

    assert first == again
    assert len(again) == 1


@pytest.mark.asyncio
async def test_recompute_window_does_not_touch_neighbors(db_session):
    """Rebuilding day D must not destroy a shift attributed to D-2."""
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 3, 7, 0))
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 3, 15, 0))
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 7, 0))
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 5, 15, 0))

    svc = _svc(db_session)
    await svc.recompute_user(user.id, date(2026, 7, 3), date(2026, 7, 3), now=NOW)
    await svc.recompute_user(user.id, D, D, now=NOW)

    shifts = await _shifts(db_session, user)
    assert len(shifts) == 2
    assert {s.work_date for s in shifts} == {date(2026, 7, 3), D}


@pytest.mark.asyncio
async def test_recompute_for_punch_uses_punch_day(db_session):
    """The bot hook: an OUT after midnight recomputes and closes yesterday's shift."""
    user = await _guard(db_session)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 5, 23, 0))
    svc = _svc(db_session)
    await svc.recompute_for_punch(user.id, datetime(2026, 7, 5, 23, 0))
    shifts = await _shifts(db_session, user)
    assert shifts[0].status == ShiftPairStatus.OPEN

    out_at = datetime(2026, 7, 6, 7, 0)
    await _punch(db_session, user, PunchDirection.OUT, out_at)
    await svc.recompute_for_punch(user.id, out_at)

    shifts = await _shifts(db_session, user)
    assert len(shifts) == 1
    assert shifts[0].status == ShiftPairStatus.COMPLETE
    assert shifts[0].work_date == D


@pytest.mark.asyncio
async def test_daily_sweep_recomputes_and_flips_stale(db_session):
    user = await _guard(db_session)
    other = await _guard(db_session, phone="0507654321")

    # user: fresh events yesterday (relative to NOW=7/7 12:00)
    await _punch(db_session, user, PunchDirection.IN, datetime(2026, 7, 6, 7, 0))
    await _punch(db_session, user, PunchDirection.OUT, datetime(2026, 7, 6, 15, 0))

    # other: an ancient OPEN shift left behind (outside the sweep window)
    repo = AttendanceShiftRepository(db_session)
    old_in = await AttendanceEventRepository(db_session).add(
        user_id=other.id,
        direction=PunchDirection.IN,
        punched_at=datetime(2026, 7, 1, 7, 0),
        source=PunchSource.TELEGRAM,
    )
    await repo.create(
        user_id=other.id,
        work_date=date(2026, 7, 1),
        check_in_at=datetime(2026, 7, 1, 7, 0),
        check_out_at=None,
        in_event_id=old_in.id,
        out_event_id=None,
        status=ShiftPairStatus.OPEN,
        recomputed_at=datetime(2026, 7, 1, 8, 0),
    )
    await db_session.commit()

    await _svc(db_session).daily_sweep(now=NOW)

    user_shifts = await _shifts(db_session, user)
    assert len(user_shifts) == 1
    assert user_shifts[0].status == ShiftPairStatus.COMPLETE

    stale = await repo.list_for_user(other.id, date(2026, 6, 30), date(2026, 7, 2))
    assert stale[0].status == ShiftPairStatus.MISSING_OUT
