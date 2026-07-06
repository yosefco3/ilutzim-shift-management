"""
Stage 3 / 02.5 step 2 — THE PRINCIPLE, as a regression suite:

    Week locking applies to PLANNING (constraint submission + board editing).
    Attendance is a record of FACTS after the fact — it is never locked.

Both directions are pinned here: every attendance operation works on a LOCKED
week, and the planning gates stay hermetically sealed exactly as before.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.attendance.constants import (
    AdjustmentAction,
    PunchDirection,
    ShiftPairStatus,
)
from app.attendance.dependencies import build_comparison_service
from app.attendance.dev_seed import seed_demo_history
from app.attendance.repositories.adjustment_repository import (
    AttendanceAdjustmentRepository,
)
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.adjustment_service import AdjustmentService
from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.services.pairing_service import PairingService
from app.attendance.services.punch_service import PunchService
from app.constants import WeekStatus
from app.exceptions import WeekLockedException
from app.models.schedule_week import ScheduleWeek
from app.models.user import User

UPCOMING = date(2026, 7, 5)
NOW = datetime(2026, 7, 6, 12, 0)


async def _guards(db_session, n=4):
    out = []
    for i in range(n):
        user = User(
            phone_number=f"05099988{i:02d}",
            first_name=f"נעול{i}",
            last_name="בדיקה",
            roles=[],
        )
        db_session.add(user)
        out.append(user)
    await db_session.commit()
    return out


async def _seeded_locked_week(db_session):
    """One seeded LOCKED demo week with a real board + punches, and a guard
    who actually has planned windows on it."""
    guards = await _guards(db_session)
    await seed_demo_history(db_session, upcoming_start=UPCOMING, weeks=1, seed=42)
    await db_session.commit()
    week = (
        await db_session.execute(
            select(ScheduleWeek).where(ScheduleWeek.status == WeekStatus.LOCKED)
        )
    ).scalars().first()
    assert week is not None
    return week, guards


def _adjustment_service(db_session) -> AdjustmentService:
    events = AttendanceEventRepository(db_session)
    return AdjustmentService(
        events,
        AttendanceAdjustmentRepository(db_session),
        PairingService(events, AttendanceShiftRepository(db_session)),
    )


# ── attendance is OPEN on a locked week ──────────────────────────────────────

@pytest.mark.asyncio
async def test_comparison_reads_a_locked_weeks_board(db_session):
    """Planned windows resolve from a LOCKED week's real board (no lock gate
    anywhere in the read path)."""
    week, guards = await _seeded_locked_week(db_session)
    comparison = await build_comparison_service(db_session)

    day_view = await comparison.get_day_all(week.start_date, now=NOW)
    assert day_view["rows"], "a seeded locked week must yield classified rows"
    assert any(r.planned for r in day_view["rows"])


@pytest.mark.asyncio
async def test_all_four_edits_work_on_a_locked_week(db_session):
    week, guards = await _seeded_locked_week(db_session)
    service = _adjustment_service(db_session)
    day = week.start_date
    guard = guards[0]

    # add a punch pair on the locked week
    adj_in = await service.add_punch(
        guard.id, PunchDirection.IN, datetime.combine(day, datetime.min.time()) + timedelta(hours=7),
        "השלמה בדיעבד", now=NOW,
    )
    in_event_id = adj_in.target_event_id
    await service.add_punch(
        guard.id, PunchDirection.OUT,
        datetime.combine(day, datetime.min.time()) + timedelta(hours=15),
        "השלמה בדיעבד", now=NOW,
    )
    # edit the in-punch's time
    await service.edit_time(
        in_event_id,
        datetime.combine(day, datetime.min.time()) + timedelta(hours=7, minutes=30),
        "תיקון לקראת שכר", now=NOW,
    )
    # approve an absence on another locked day
    await service.mark_absence(guard.id, day + timedelta(days=1), "מחלה מאושרת")
    await db_session.commit()

    trail = await service.history(guard.id, day)
    actions = {a.action for a in trail}
    assert AdjustmentAction.ADD_PUNCH in actions
    assert AdjustmentAction.EDIT_TIME in actions

    shifts = await AttendanceShiftRepository(db_session).list_for_user(
        guard.id, day, day
    )
    edited = [s for s in shifts if s.check_in_at.minute == 30]
    assert edited and edited[0].status == ShiftPairStatus.COMPLETE


@pytest.mark.asyncio
async def test_bot_punch_records_while_the_week_is_locked(db_session):
    """The live week is LOCKED from the moment it starts — punching must work."""
    week, guards = await _seeded_locked_week(db_session)
    config = AttendanceConfig(
        grace_minutes=15, big_gap_minutes=60, site_lat=None, site_lng=None,
        site_radius_m=150, admin_alerts_enabled=False, admin_chat_id="",
        company_name="ספרא",
    )
    punch = PunchService(AttendanceEventRepository(db_session), config)
    outcome = await punch.record_punch(
        guards[0].id, PunchDirection.IN,
        datetime.combine(week.start_date, datetime.min.time()) + timedelta(hours=6, minutes=50),
    )
    assert outcome.created is True


# ── planning stays SEALED on a locked week ───────────────────────────────────

@pytest.mark.asyncio
async def test_constraint_submission_still_hermetically_locked(db_session):
    """The existing gate is untouched: LOCKED rejects submissions for everyone,
    even an admin with override_lock."""
    from app.repositories.schedule_week_repository import ScheduleWeekRepository
    from app.repositories.submission_repository import SubmissionRepository
    from app.repositories.user_repository import UserRepository
    from app.schemas.submission_schemas import DayStatusInput, SubmissionCreate
    from app.services.submission_service import SubmissionService

    week, guards = await _seeded_locked_week(db_session)
    service = SubmissionService(
        SubmissionRepository(db_session),
        UserRepository(db_session),
        ScheduleWeekRepository(db_session),
    )
    data = SubmissionCreate(
        user_id=guards[0].id,
        week_id=week.id,
        days=[DayStatusInput(date=week.start_date, is_available=False, shifts=[])],
    )

    with pytest.raises(WeekLockedException):
        await service.create_submission(data)
    with pytest.raises(WeekLockedException):
        await service.create_submission(data, override_lock=True)


@pytest.mark.asyncio
async def test_locked_is_still_terminal(db_session):
    """No status transition escapes LOCKED (reopening stays impossible)."""
    from app.exceptions import InvalidTransitionException
    from app.repositories.schedule_week_repository import ScheduleWeekRepository
    from app.repositories.user_repository import UserRepository
    from app.services.week_service import WeekService

    week, _ = await _seeded_locked_week(db_session)
    service = WeekService(
        ScheduleWeekRepository(db_session), UserRepository(db_session)
    )
    for target in (WeekStatus.OPEN, WeekStatus.CLOSED):
        with pytest.raises(InvalidTransitionException):
            await service.change_week_status(week.id, target)
