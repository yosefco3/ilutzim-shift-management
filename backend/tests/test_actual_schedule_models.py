"""
Model-level tests for the actual-schedule layer (step 01).

Covers the three tables' relationships and integrity rules: week → copy →
positions → assignments cascade, one-copy-per-week uniqueness, and the
no-duplicate-guard-in-cell constraint.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.schedule_builder.models import (
    ActualAssignment,
    ActualPosition,
    ActualSchedule,
)


async def _make_week(db_session, offset_days=0) -> ScheduleWeek:
    from datetime import timedelta

    from app.utils.date_utils import week_range

    start, end = week_range(date.today() + timedelta(days=offset_days))
    week = ScheduleWeek(start_date=start, end_date=end, status=WeekStatus.LOCKED)
    db_session.add(week)
    await db_session.commit()
    await db_session.refresh(week)
    return week


async def _make_guard(db_session) -> User:
    guard = User(
        first_name="ישראל",
        last_name="ישראלי",
        phone_number=f"05{uuid.uuid4().hex[:8]}",
    )
    db_session.add(guard)
    await db_session.commit()
    await db_session.refresh(guard)
    return guard


async def _make_full_copy(db_session, week, guard):
    """Week → actual schedule → one position → one assignment."""
    actual = ActualSchedule(week_id=week.id, seed_source="rollover")
    db_session.add(actual)
    await db_session.flush()

    position = ActualPosition(
        actual_schedule_id=actual.id,
        name="ארנונה",
        day_schedules={"0": {"start": "07:00", "end": "15:00"}},
        display_order=1,
    )
    db_session.add(position)
    await db_session.flush()

    assignment = ActualAssignment(
        actual_schedule_id=actual.id,
        actual_position_id=position.id,
        day_index=0,
        user_id=guard.id,
    )
    db_session.add(assignment)
    await db_session.commit()
    return actual, position, assignment


@pytest.mark.asyncio
async def test_full_chain_persists(db_session):
    week = await _make_week(db_session)
    guard = await _make_guard(db_session)
    actual, position, assignment = await _make_full_copy(db_session, week, guard)

    assert actual.seed_source == "rollover"
    assert actual.seeded_at is not None
    assert position.source_position_id is None  # ad-hoc by default
    assert assignment.segment_start is None


@pytest.mark.asyncio
async def test_deleting_week_cascades_the_whole_copy(db_session):
    week = await _make_week(db_session)
    guard = await _make_guard(db_session)
    await _make_full_copy(db_session, week, guard)

    await db_session.delete(week)
    await db_session.commit()

    for model in (ActualSchedule, ActualPosition, ActualAssignment):
        rows = (await db_session.execute(select(model))).scalars().all()
        assert rows == [], f"{model.__name__} rows survived week deletion"


@pytest.mark.asyncio
async def test_deleting_position_cascades_its_assignments_only(db_session):
    week = await _make_week(db_session)
    guard = await _make_guard(db_session)
    actual, position, _ = await _make_full_copy(db_session, week, guard)

    other = ActualPosition(
        actual_schedule_id=actual.id, name="קומה 6", day_schedules={},
    )
    db_session.add(other)
    await db_session.commit()

    await db_session.delete(position)
    await db_session.commit()

    assignments = (await db_session.execute(select(ActualAssignment))).scalars().all()
    positions = (await db_session.execute(select(ActualPosition))).scalars().all()
    assert assignments == []
    assert [p.name for p in positions] == ["קומה 6"]


@pytest.mark.asyncio
async def test_one_actual_schedule_per_week(db_session):
    week = await _make_week(db_session)
    db_session.add(ActualSchedule(week_id=week.id))
    await db_session.commit()

    db_session.add(ActualSchedule(week_id=week.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_same_guard_twice_in_cell_rejected(db_session):
    week = await _make_week(db_session)
    guard = await _make_guard(db_session)
    actual, position, _ = await _make_full_copy(db_session, week, guard)
    # Capture plain ids — the rollback below expires the ORM objects.
    actual_id, position_id = actual.id, position.id

    db_session.add(
        ActualAssignment(
            actual_schedule_id=actual_id,
            actual_position_id=position_id,
            day_index=0,
            user_id=guard.id,
            segment_start="15:00",
            segment_end="19:00",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # A *different* guard in the same cell is fine (tiling).
    other_guard = await _make_guard(db_session)
    db_session.add(
        ActualAssignment(
            actual_schedule_id=actual_id,
            actual_position_id=position_id,
            day_index=0,
            user_id=other_guard.id,
        )
    )
    await db_session.commit()
