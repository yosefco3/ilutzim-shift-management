"""Integration tests for committing a parsed import into the availability model.

Runs against real repositories + services on in-memory SQLite, exercising the
actual write path (find-or-create guard by name, upsert submission per week).
"""

import os
import uuid
from datetime import date, time, timedelta
from pathlib import Path

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
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.services.constraints_import.commit import (
    ConstraintsCommitService,
    WeekNotFoundError,
)
from app.services.constraints_import.parser import parse_constraints_xlsx
from app.services.submission_service import SubmissionService

FIXTURE = Path(__file__).parent / "fixtures" / "דוגמה_אילוצים_מאבטחים.xlsx"

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
async def user_repo(db_session):
    return UserRepository(db_session)


@pytest_asyncio.fixture
async def commit_service(db_session):
    sub_service = SubmissionService(
        submission_repo=SubmissionRepository(db_session),
        user_repo=UserRepository(db_session),
        week_repo=ScheduleWeekRepository(db_session),
    )
    return ConstraintsCommitService(
        user_repo=UserRepository(db_session),
        week_repo=ScheduleWeekRepository(db_session),
        submission_service=sub_service,
    )


@pytest_asyncio.fixture
async def target_week(db_session):
    # Matches the sample file's title range (2026-06-14 .. 2026-06-20).
    # Constraint import runs while the week is CLOSED — the admin editing on
    # behalf of guards (override_lock). A LOCKED week is final and rejects edits.
    w = ScheduleWeek(
        start_date=date(2026, 6, 14),
        end_date=date(2026, 6, 20),
        status=WeekStatus.CLOSED,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


def _parsed():
    return parse_constraints_xlsx(FIXTURE.read_bytes())


async def _count(db_session, model):
    result = await db_session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_commit_creates_submissions_for_all_guards(
    db_session, commit_service, target_week
):
    resp = await commit_service.commit(_parsed())

    assert resp.summary.imported == 5
    assert resp.summary.created_new == 5  # none existed beforehand
    assert resp.summary.errors == []
    assert resp.summary.week_start == date(2026, 6, 14)

    # One submission per guard, with the right shift windows persisted.
    from app.models.weekly_submission import WeeklySubmission
    assert await _count(db_session, WeeklySubmission) == 5

    sub_repo = SubmissionRepository(db_session)
    user_repo = UserRepository(db_session)
    users = {u.full_name: u for u in await user_repo.get_all_users()}

    avi = await sub_repo.get_submission(users["אבי כהן"].id, target_week.id)
    sunday = next(d for d in avi.daily_statuses if d.date == date(2026, 6, 14))
    morning = next(w for w in sunday.shift_windows if w.shift_type == ShiftType.MORNING)
    assert (morning.start_time, morning.end_time) == (time(7, 0), time(16, 0))

    beni = await sub_repo.get_submission(users["בני לוי"].id, target_week.id)
    b_sunday = next(d for d in beni.daily_statuses if d.date == date(2026, 6, 14))
    night = next(w for w in b_sunday.shift_windows if w.shift_type == ShiftType.NIGHT)
    assert (night.start_time, night.end_time) == (time(23, 0), time(7, 0))


@pytest.mark.asyncio
async def test_existing_guard_is_matched_not_duplicated(
    db_session, commit_service, target_week
):
    # Pre-create one guard with the exact full name from the file.
    existing = User(
        phone_number="0501234567",
        first_name="אבי",
        last_name="כהן",
        roles=[],
        is_active=True,
    )
    db_session.add(existing)
    await db_session.commit()

    resp = await commit_service.commit(_parsed())

    assert resp.summary.imported == 5
    assert resp.summary.created_new == 4  # אבי כהן already existed

    # No duplicate "אבי כהן".
    names = [u.full_name for u in await UserRepository(db_session).get_all_users()]
    assert names.count("אבי כהן") == 1


@pytest.mark.asyncio
async def test_guard_matched_by_id_even_when_name_differs(
    db_session, commit_service, target_week
):
    """When the file carries the guard's DB id (the מזהה column), the importer
    matches that exact guard even if the name in the sheet was edited."""
    from app.services.constraints_import.parser import (
        Cell, CellKind, ParsedGuard, ParsedImport,
    )

    existing = User(
        phone_number="0501234567",
        first_name="אבי",
        last_name="כהן",
        roles=["AHMASH"],
        is_active=True,
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    parsed = ParsedImport(
        week_start=target_week.start_date,
        week_end=target_week.end_date,
        guards=[
            ParsedGuard(
                name="אבי כהן-לוי",  # renamed in the sheet — id should still win
                phone=None,
                notes=None,
                guard_id=str(existing.id),
                cells={0: {ShiftType.MORNING: Cell(CellKind.ALL_DAY)}},
            )
        ],
    )

    resp = await commit_service.commit(parsed)

    assert resp.summary.imported == 1
    assert resp.summary.created_new == 0  # matched by id, not created
    users = await UserRepository(db_session).get_all_users()
    assert len(users) == 1  # no duplicate guard created
    sub = await SubmissionRepository(db_session).get_submission(
        existing.id, target_week.id
    )
    assert sub is not None  # submission tied to the existing guard


@pytest.mark.asyncio
async def test_reimport_is_upsert_no_duplicates(
    db_session, commit_service, target_week
):
    from app.models.weekly_submission import WeeklySubmission

    await commit_service.commit(_parsed())
    await commit_service.commit(_parsed())  # second import

    assert await _count(db_session, WeeklySubmission) == 5  # upsert, not 10
    users = await UserRepository(db_session).get_all_users()
    assert len(users) == 5  # guards not recreated


@pytest.mark.asyncio
async def test_missing_week_raises_clear_error(db_session, commit_service):
    # No week seeded → resolve fails with a clear error and writes nothing.
    with pytest.raises(WeekNotFoundError):
        await commit_service.commit(_parsed())

    from app.models.weekly_submission import WeeklySubmission
    assert await _count(db_session, WeeklySubmission) == 0
    assert await _count(db_session, User) == 0
