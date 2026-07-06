"""Tests for ensure_initial_week seed function."""

import pytest
from datetime import date

from app.constants import WeekStatus
from app.seed import ensure_initial_week
from app.utils.date_utils import week_range


@pytest.mark.asyncio
async def test_creates_week_when_db_empty(db_session):
    """Should create a closed week for the upcoming period when no weeks exist."""
    await ensure_initial_week(db_session)

    from app.repositories.schedule_week_repository import ScheduleWeekRepository
    repo = ScheduleWeekRepository(db_session)
    all_weeks = await repo.get_all()
    assert len(all_weeks) == 1

    week = all_weeks[0]
    today = date.today()
    expected_start, expected_end = week_range(today)
    assert week.start_date == expected_start
    assert week.end_date == expected_end
    assert week.status == WeekStatus.CLOSED


@pytest.mark.asyncio
async def test_skips_when_weeks_exist(db_session, sample_week):
    """Should NOT create a week when one already exists."""
    await ensure_initial_week(db_session)

    from app.repositories.schedule_week_repository import ScheduleWeekRepository
    repo = ScheduleWeekRepository(db_session)
    all_weeks = await repo.get_all()
    assert len(all_weeks) == 1  # only the sample_week
    assert all_weeks[0].id == sample_week.id