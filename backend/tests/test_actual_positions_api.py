"""
Step 06 — actual-board position editing: ad-hoc add, edit, remove, and the
"save as profile" promotion. All service-level on the real (in-memory) DB.
"""

import uuid
from datetime import timedelta

import pytest

from app.constants import WeekStatus
from app.exceptions import ConflictException
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment
from app.schedule_builder.repositories.actual_schedule_repository import (
    ActualScheduleRepository,
)
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.repositories.week_profile_repository import (
    WeekProfileRepository,
)
from app.schedule_builder.services.actual_schedule_service import (
    ActualScheduleService,
)
from app.schedule_builder.services.week_profile_service import WeekProfileService
from app.utils.date_utils import today_il


def _service(session) -> ActualScheduleService:
    return ActualScheduleService(
        ActualScheduleRepository(session),
        ScheduleWeekRepository(session),
        WeekProfileService(
            WeekProfileRepository(session),
            ProfileRepository(session),
            ScheduleWeekRepository(session),
        ),
        PositionRepository(session),
        AssignmentRepository(session),
        profile_repo=ProfileRepository(session),
    )


async def _planned_week(db_session):
    """A started week with a one-position planned profile."""
    start = today_il() - timedelta(days=7)
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
    planned_position = Position(
        profile_id=profile.id, name="ארנונה",
        day_schedules={"0": {"start": "07:00", "end": "15:00"}},
        required_attributes=["ARMED"], display_order=1,
    )
    db_session.add(planned_position)
    await db_session.commit()
    return week, profile, planned_position


@pytest.mark.asyncio
async def test_adhoc_position_appears_on_board_and_read_model(db_session):
    week, _, _ = await _planned_week(db_session)
    service = _service(db_session)

    added = await service.add_position(
        week.id,
        name="אבטחת אירוע במתנס",
        day_schedules={"3": {"start": "16:00", "end": "20:00"}},
    )
    assert added.source_position_id is None

    board = await service.get_board(week.id)
    adhoc = [r for r in board["rows"] if r["is_adhoc"]]
    assert [r["name"] for r in adhoc] == ["אבטחת אירוע במתנס"]

    # A guard placed on it flows into the shared read model (→ comparison).
    guard = User(phone_number="0501111111", first_name="נתן", last_name="כהן")
    db_session.add(guard)
    await db_session.commit()
    await service.assign(added.id, 3, guard.id)

    from tests.test_actual_export_parity import _actual_export

    schedule = await _actual_export(db_session).get_week_schedule(week.id)
    natan = next(g for g in schedule.by_guard if g.user_name == guard.full_name)
    assert [(s.position_name, s.start, s.end) for s in natan.shifts] == [
        ("אבטחת אירוע במתנס", "16:00", "20:00")
    ]


@pytest.mark.asyncio
async def test_remove_position_cascades_only_its_assignments(db_session):
    week, _, planned_position = await _planned_week(db_session)
    service = _service(db_session)

    board = await service.get_board(week.id)
    (copied_row,) = board["rows"]
    guard = User(phone_number="0502222222", first_name="דנה", last_name="לוי")
    db_session.add(guard)
    await db_session.commit()
    await service.assign(copied_row["position_id"], 0, guard.id)

    await service.remove_position(copied_row["position_id"])

    board = await service.get_board(week.id)
    assert board["rows"] == []
    assert board["assignments"] == []
    # The planning layer is untouched — the profile still has its position.
    assert await PositionRepository(db_session).get_by_id(planned_position.id)


@pytest.mark.asyncio
async def test_narrowing_window_keeps_assignment_with_warning(db_session):
    week, _, _ = await _planned_week(db_session)
    service = _service(db_session)

    board = await service.get_board(week.id)
    (row,) = board["rows"]
    guard = User(phone_number="0503333333", first_name="רן", last_name="גל")
    db_session.add(guard)
    await db_session.commit()
    assignment = await service.assign(
        row["position_id"], 0, guard.id, "07:00", "15:00"
    )

    # Narrow the day window to 07–12; the 07–15 segment no longer fits.
    await service.update_position(
        row["position_id"],
        day_schedules={"0": {"start": "07:00", "end": "12:00"}},
    )

    board = await service.get_board(week.id)
    assert len(board["assignments"]) == 1  # kept, not silently deleted
    outside = [
        w for w in board["warnings"] if w["type"] == "assignments_outside_window"
    ]
    assert len(outside) == 1 and outside[0]["reason"] == "segment_outside_window"

    # Dropping the day entirely → the same warning, "inactive_day" flavour.
    await service.update_position(row["position_id"], day_schedules={})
    board = await service.get_board(week.id)
    outside = [
        w for w in board["warnings"] if w["type"] == "assignments_outside_window"
    ]
    assert len(outside) == 1 and outside[0]["reason"] == "inactive_day"


@pytest.mark.asyncio
async def test_event_flag_and_count_semantics(db_session):
    week, _, _ = await _planned_week(db_session)
    service = _service(db_session)

    added = await service.add_position(
        week.id, name="רענון",
        day_schedules={"2": {"start": "09:00", "end": "12:00"}},
        is_event=True, event_required_count=4,
    )
    assert added.event_required_count == 4

    # Turning the event flag off clears the count (mirrors the planning rule).
    updated = await service.update_position(added.id, is_event=False)
    assert updated.event_required_count is None


@pytest.mark.asyncio
async def test_save_as_profile_clones_the_actual_board(db_session):
    week, _, _ = await _planned_week(db_session)
    service = _service(db_session)
    await service.add_position(
        week.id, name="אבטחת אירוע במתנס",
        day_schedules={"3": {"start": "16:00", "end": "20:00"}},
    )

    profile = await service.save_as_profile(week.id, "שגרה + אירוע מתנס")

    cloned = await PositionRepository(db_session).get_by_profile(profile.id)
    assert [(p.name, p.display_order) for p in cloned] == [
        ("ארנונה", 1), ("אבטחת אירוע במתנס", 2),
    ]
    assert cloned[0].required_attributes == ["ARMED"]
    assert cloned[0].day_schedules == {"0": {"start": "07:00", "end": "15:00"}}
    assert profile.is_default is False

    # Duplicate name → friendly conflict.
    with pytest.raises(ConflictException):
        await service.save_as_profile(week.id, "שגרה + אירוע מתנס")
