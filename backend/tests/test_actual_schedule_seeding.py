"""
Tests for ActualScheduleService.ensure_for_week (step 02) — the birth of the
week's editable execution copy, and its idempotency guarantees.
"""

from datetime import date, timedelta

import pytest

from app.constants import WeekStatus
from app.exceptions import WeekNotFoundException
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models import ActualAssignment, ActualPosition
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment
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
    ActualScheduleNotAvailableException,
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
    )


async def _make_week(db_session, *, started=True, status=WeekStatus.LOCKED):
    offset = -7 if started else 7
    start = today_il() + timedelta(days=offset)
    week = ScheduleWeek(
        start_date=start, end_date=start + timedelta(days=6), status=status,
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _make_planned_board(db_session, week):
    """Profile linked to the week + two positions + two assignments."""
    profile = ActivationProfile(name="שגרה", is_default=True)
    db_session.add(profile)
    await db_session.flush()
    db_session.add(WeekProfileAssignment(week_id=week.id, profile_id=profile.id))

    arnona = Position(
        profile_id=profile.id,
        name="ארנונה",
        day_schedules={str(d): {"start": "07:00", "end": "15:00"} for d in range(6)},
        required_attributes=["ARMED"],
        display_order=1,
    )
    event = Position(
        profile_id=profile.id,
        name="ישיבת מועצה",
        day_schedules={"2": {"start": "17:00", "end": "21:00"}},
        display_order=2,
        is_event=True,
        event_required_count=4,
    )
    db_session.add_all([arnona, event])
    await db_session.flush()

    guard = User(phone_number="0501111111", first_name="נתן", last_name="כהן")
    db_session.add(guard)
    await db_session.flush()

    db_session.add_all([
        ScheduleAssignment(
            week_id=week.id, position_id=arnona.id, day_index=0, user_id=guard.id,
        ),
        ScheduleAssignment(
            week_id=week.id, position_id=arnona.id, day_index=1, user_id=guard.id,
            segment_start="07:00", segment_end="11:00",
        ),
    ])
    await db_session.commit()
    return profile, arnona, event, guard


@pytest.mark.asyncio
async def test_seed_copies_planned_board_field_for_field(db_session):
    week = await _make_week(db_session)
    profile, arnona, event, guard = await _make_planned_board(db_session, week)

    service = _service(db_session)
    actual = await service.ensure_for_week(week.id, source="rollover")

    assert actual.seed_source == "rollover"
    positions = {p.name: p for p in actual.positions}
    assert set(positions) == {"ארנונה", "ישיבת מועצה"}

    copy = positions["ארנונה"]
    assert copy.day_schedules == arnona.day_schedules
    assert copy.required_attributes == ["ARMED"]
    assert copy.display_order == 1
    assert copy.source_position_id == arnona.id

    event_copy = positions["ישיבת מועצה"]
    assert event_copy.is_event is True
    assert event_copy.event_required_count == 4

    repo = ActualScheduleRepository(db_session)
    assignments = await repo.list_assignments(actual.id)
    assert len(assignments) == 2
    segmented = next(a for a in assignments if a.segment_start)
    assert (segmented.segment_start, segmented.segment_end) == ("07:00", "11:00")
    assert all(a.actual_position_id == copy.id for a in assignments)
    assert all(a.user_id == guard.id for a in assignments)


@pytest.mark.asyncio
async def test_ensure_is_idempotent_and_never_overwrites_edits(db_session):
    week = await _make_week(db_session)
    await _make_planned_board(db_session, week)

    service = _service(db_session)
    actual = await service.ensure_for_week(week.id)
    first_id = actual.id

    # Edit the copy: drop one assignment + add an ad-hoc position.
    repo = ActualScheduleRepository(db_session)
    assignments = await repo.list_assignments(actual.id)
    await db_session.delete(assignments[0])
    db_session.add(ActualPosition(
        actual_schedule_id=actual.id, name="אירוע פתע", day_schedules={},
    ))
    await db_session.commit()

    again = await service.ensure_for_week(week.id, source="rollover")
    assert again.id == first_id
    assert again.seed_source == "lazy"  # original source survives
    assert len(await repo.list_assignments(first_id)) == 1
    names = {p.name for p in await repo.list_positions(first_id)}
    assert "אירוע פתע" in names  # the edit survived
    assert len(names) == 3  # nothing was re-seeded on top


@pytest.mark.asyncio
async def test_future_week_is_rejected(db_session):
    week = await _make_week(db_session, started=False, status=WeekStatus.CLOSED)
    await _make_planned_board(db_session, week)

    with pytest.raises(ActualScheduleNotAvailableException):
        await _service(db_session).ensure_for_week(week.id)


@pytest.mark.asyncio
async def test_unknown_week_raises(db_session):
    import uuid

    with pytest.raises(WeekNotFoundException):
        await _service(db_session).ensure_for_week(uuid.uuid4())


@pytest.mark.asyncio
async def test_week_without_profile_seeds_empty(db_session):
    week = await _make_week(db_session)

    actual = await _service(db_session).ensure_for_week(week.id)
    assert actual.positions == []


@pytest.mark.asyncio
async def test_rollover_seeds_the_locking_week(db_session):
    """lock_expired_open_weeks births the copy for the week it finalizes."""
    from app.services.week_service import WeekService

    week = await _make_week(db_session, started=True, status=WeekStatus.OPEN)
    week.opened_at = week.start_date  # a week whose submission window ran
    await _make_planned_board(db_session, week)

    week_service = WeekService(
        ScheduleWeekRepository(db_session),
        actual_schedule_service=_service(db_session),
    )
    await week_service.lock_expired_open_weeks()

    repo = ActualScheduleRepository(db_session)
    actual = await repo.get_by_week(week.id)
    assert actual is not None
    assert actual.seed_source == "rollover"
    assert len(actual.positions) == 2


@pytest.mark.asyncio
async def test_rollover_survives_seeding_failure(db_session):
    """A seeder blow-up must not break the lock itself."""
    from unittest.mock import AsyncMock

    from app.services.week_service import WeekService

    week = await _make_week(db_session, started=True, status=WeekStatus.OPEN)
    week.opened_at = week.start_date
    await db_session.commit()

    broken = AsyncMock()
    broken.ensure_for_week.side_effect = RuntimeError("boom")
    week_service = WeekService(
        ScheduleWeekRepository(db_session), actual_schedule_service=broken,
    )
    await week_service.lock_expired_open_weeks()

    refreshed = await ScheduleWeekRepository(db_session).get_by_id(week.id)
    assert refreshed.status == WeekStatus.LOCKED
