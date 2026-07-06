"""
Integration tests for submission persistence (regression for the bug where
``create_submission`` saved only the submission row and dropped days/shifts).

These run against the real repositories + service on an in-memory SQLite DB,
so they exercise the actual write path — not mocks. They guard that every
piece the frontend sends is persisted: days, shifts, hours and notes.
"""

import os
import uuid
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("APP_URL", "http://localhost:3000")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("ENVIRONMENT", "dev")

from app.constants import ShiftType, UserRole, WeekStatus
from app.models.base import Base
from app.models.daily_status import DailyStatus
from app.models.schedule_week import ScheduleWeek
from app.models.shift_window import ShiftWindow
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.submission_schemas import (
    DayStatusInput,
    ShiftWindowInput,
    SubmissionCreate,
)
from app.services.submission_service import SubmissionService

TEST_DB_URL = "sqlite+aiosqlite://"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def service(db_session):
    return SubmissionService(
        submission_repo=SubmissionRepository(db_session),
        user_repo=UserRepository(db_session),
        week_repo=ScheduleWeekRepository(db_session),
    )


@pytest_asyncio.fixture
async def user(db_session):
    u = User(
        phone_number="0500000000",
        first_name="דנה",
        last_name="כהן",
        roles=[],
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def open_week(db_session):
    start = date(2026, 6, 14)  # a Sunday
    w = ScheduleWeek(
        start_date=start,
        end_date=start + timedelta(days=6),
        status=WeekStatus.OPEN,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


def _make_create(user_id, week_id, week_start):
    """One available day with a morning shift, plus a note."""
    return SubmissionCreate(
        user_id=user_id,
        week_id=week_id,
        general_notes="לא זמין בערב",
        days=[
            DayStatusInput(
                date=week_start,
                is_available=True,
                shifts=[
                    ShiftWindowInput(
                        shift_type=ShiftType.MORNING,
                        start_time=time(6, 0),
                        end_time=time(14, 0),
                    )
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_create_submission_persists_days_shifts_and_notes(
    db_session, service, user, open_week
):
    data = _make_create(user.id, open_week.id, open_week.start_date)

    resp = await service.create_submission(data)

    # Response carries the full structure back (days mapped from daily_statuses)
    assert resp.general_notes == "לא זמין בערב"
    assert len(resp.days) == 1
    assert resp.days[0].is_available is True
    assert len(resp.days[0].shift_windows) == 1
    sw = resp.days[0].shift_windows[0]
    assert sw.shift_type == ShiftType.MORNING
    assert sw.start_time == time(6, 0)
    assert sw.end_time == time(14, 0)

    # And the rows actually exist in the DB (the original bug left these at 0)
    ds_count = await db_session.scalar(select(func.count()).select_from(DailyStatus))
    sw_count = await db_session.scalar(select(func.count()).select_from(ShiftWindow))
    assert ds_count == 1
    assert sw_count == 1


@pytest.mark.asyncio
async def test_detailed_lists_submitter_with_shift_detail(
    service, user, open_week
):
    await service.create_submission(_make_create(user.id, open_week.id, open_week.start_date))

    detailed = await service.get_week_submissions_detailed(open_week.id)

    assert len(detailed["missing"]) == 0
    assert len(detailed["submitted"]) == 1
    row = detailed["submitted"][0]
    assert row.full_name == "דנה כהן"
    assert row.general_notes == "לא זמין בערב"
    assert row.days[0].shift_windows[0].start_time == time(6, 0)


@pytest.mark.asyncio
async def test_resubmit_replaces_days_without_duplicating(
    db_session, service, user, open_week
):
    await service.create_submission(_make_create(user.id, open_week.id, open_week.start_date))

    # Re-submit with a different shift — should replace, not append
    second = SubmissionCreate(
        user_id=user.id,
        week_id=open_week.id,
        general_notes="עודכן",
        days=[
            DayStatusInput(
                date=open_week.start_date,
                is_available=True,
                shifts=[
                    ShiftWindowInput(
                        shift_type=ShiftType.NIGHT,
                        start_time=time(22, 0),
                        end_time=time(6, 0),
                    )
                ],
            )
        ],
    )
    resp = await service.create_submission(second)

    assert resp.general_notes == "עודכן"
    sub_count = await db_session.scalar(
        select(func.count()).select_from(DailyStatus)
    )
    assert sub_count == 1  # replaced, not duplicated
    assert resp.days[0].shift_windows[0].shift_type == ShiftType.NIGHT


@pytest.mark.asyncio
async def test_grid_includes_inactive_guards_with_flag(
    db_session, service, user, open_week
):
    # `user` is active; add a second, inactive guard.
    inactive = User(
        phone_number="0500000001",
        first_name="רון",
        last_name="לוי",
        roles=[],
        is_active=False,
    )
    db_session.add(inactive)
    await db_session.commit()
    await db_session.refresh(inactive)

    grid = await service.get_week_submissions_grid(open_week.id)

    by_id = {row.user_id: row for row in grid}
    # Both active and inactive guards appear, each with the correct flag.
    assert by_id[user.id].is_active is True
    assert by_id[inactive.id].is_active is False


@pytest.mark.asyncio
async def test_grid_reports_telegram_link_status(
    db_session, service, user, open_week
):
    """has_telegram reflects whether the guard ever linked Telegram — the reports
    page flags the ones the admin fills constraints for by hand."""
    linked = User(
        phone_number="0500000002",
        first_name="נועה",
        last_name="בר",
        roles=[],
        is_active=True,
        telegram_id="tg-noa",
    )
    db_session.add(linked)
    await db_session.commit()
    await db_session.refresh(linked)

    grid = await service.get_week_submissions_grid(open_week.id)

    by_id = {row.user_id: row for row in grid}
    # `user` fixture never linked Telegram; `linked` did.
    assert by_id[user.id].has_telegram is False
    assert by_id[linked.id].has_telegram is True


@pytest.mark.asyncio
async def test_get_submission_counts_groups_by_week(
    db_session, service, user, open_week
):
    """Regression: the weeks page showed '0 הגשות' because no count was returned.

    The count is keyed by week_id and reflects the number of guards who submitted.
    """
    # No submissions yet → week absent from the map (UI falls back to 0).
    assert await service.get_submission_counts() == {}

    # One guard submits for the open week.
    await service.create_submission(
        _make_create(user.id, open_week.id, open_week.start_date)
    )

    # A second guard submits for the same week.
    other = User(
        phone_number="0500000002",
        first_name="נועה",
        last_name="בר",
        roles=[],
        is_active=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    await service.create_submission(
        _make_create(other.id, open_week.id, open_week.start_date)
    )

    counts = await service.get_submission_counts()
    assert counts == {open_week.id: 2}
