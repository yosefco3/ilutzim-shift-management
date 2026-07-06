"""
Tests for the ScheduleAssignment model (part B — schedule builder, task 05).
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment


async def _make_week(db_session, start=date(2026, 7, 5)):
    week = ScheduleWeek(
        start_date=start,
        end_date=date(start.year, start.month, start.day + 6),
        status=WeekStatus.OPEN,
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _make_position(db_session, name="ארנונה"):
    profile = ActivationProfile(name="שגרה")
    db_session.add(profile)
    await db_session.flush()
    pos = Position(
        profile_id=profile.id,
        name=name,
        day_schedules={"0": {"start": "07:00", "end": "15:00"}},
    )
    db_session.add(pos)
    await db_session.flush()
    return pos


async def _make_user(db_session, phone="0501111111", roles=None):
    user = User(
        phone_number=phone,
        first_name="נתן",
        last_name="כהן",
        roles=roles or [],
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestScheduleAssignmentModel:
    async def test_create_defaults_no_segment(self, db_session):
        """An assignment fills a cell; segment is optional (null = whole window)."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session)
        a = ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=0, user_id=user.id
        )
        db_session.add(a)
        await db_session.flush()
        await db_session.refresh(a)

        assert isinstance(a.id, uuid.UUID)
        assert a.segment_start is None and a.segment_end is None

    async def test_tiling_two_guards_same_cell(self, db_session):
        """A cell may hold several guards (tiling) — each with its own segment."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        u1 = await _make_user(db_session, phone="0501111111")
        u2 = await _make_user(db_session, phone="0502222222")
        db_session.add_all([
            ScheduleAssignment(
                week_id=week.id, position_id=pos.id, day_index=0, user_id=u1.id,
                segment_start="19:00", segment_end="01:00",
            ),
            ScheduleAssignment(
                week_id=week.id, position_id=pos.id, day_index=0, user_id=u2.id,
                segment_start="01:00", segment_end="07:00",
            ),
        ])
        await db_session.flush()

        rows = (
            await db_session.execute(
                select(ScheduleAssignment).where(ScheduleAssignment.week_id == week.id)
            )
        ).scalars().all()
        assert len(rows) == 2

    async def test_same_guard_twice_in_cell_rejected(self, db_session):
        """The UNIQUE (week, position, day, user) forbids duplicating a guard."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session)
        db_session.add(ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=0, user_id=user.id
        ))
        await db_session.flush()

        db_session.add(ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=0, user_id=user.id
        ))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_same_guard_other_day_allowed(self, db_session):
        """The same guard may fill the same position on a different day."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session)
        db_session.add(ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=0, user_id=user.id
        ))
        await db_session.flush()
        db_session.add(ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=1, user_id=user.id
        ))
        await db_session.flush()  # no IntegrityError
