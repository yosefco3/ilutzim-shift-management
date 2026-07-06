"""
Tests for the WeekProfileAssignment model (part B — schedule builder).
"""

import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment


async def _make_week(db_session, start=date(2026, 7, 5)):
    week = ScheduleWeek(
        start_date=start,
        end_date=date(start.year, start.month, start.day + 6),
        status=WeekStatus.OPEN,
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _make_profile(db_session, name="שגרה"):
    profile = ActivationProfile(name=name)
    db_session.add(profile)
    await db_session.flush()
    return profile


class TestWeekProfileAssignmentModel:
    async def test_create(self, db_session):
        """An assignment binds one week to one profile."""
        week = await _make_week(db_session)
        profile = await _make_profile(db_session)
        link = WeekProfileAssignment(week_id=week.id, profile_id=profile.id)
        db_session.add(link)
        await db_session.flush()
        await db_session.refresh(link)

        assert isinstance(link.id, uuid.UUID)
        assert link.week_id == week.id
        assert link.profile_id == profile.id

    async def test_week_id_is_unique(self, db_session):
        """A week may have at most one explicit assignment."""
        week = await _make_week(db_session)
        p1 = await _make_profile(db_session, name="שגרה")
        p2 = await _make_profile(db_session, name="חג")
        db_session.add(WeekProfileAssignment(week_id=week.id, profile_id=p1.id))
        await db_session.flush()

        db_session.add(WeekProfileAssignment(week_id=week.id, profile_id=p2.id))
        with pytest.raises(IntegrityError):
            await db_session.flush()
