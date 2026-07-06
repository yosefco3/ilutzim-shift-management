"""
Tests for the repository layer.
"""

import os
import uuid
from datetime import date, time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set test env before importing app
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("APP_URL", "http://localhost:3000")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("ENVIRONMENT", "dev")

from app.models.base import Base
from app.models.user import User
from app.models.schedule_week import ScheduleWeek
from app.models.weekly_submission import WeeklySubmission
from app.models.daily_status import DailyStatus
from app.models.shift_window import ShiftWindow
from app.models.admin import Admin
from app.models.system_setting import SystemSetting
from app.constants import WeekStatus, ShiftType, AdminRole, UserRole

from app.repositories.user_repository import UserRepository
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.admin_repository import AdminRepository
from app.repositories.system_settings_repository import SystemSettingsRepository

# In-memory SQLite
TEST_DB_URL = "sqlite+aiosqlite://"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session():
    """Yield a clean in-memory DB session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ──────────────── UserRepository ────────────────


class TestUserRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(
            phone_number="0501234567",
            first_name="John",
            last_name="Doe",
            is_active=True,
            roles=[],
        )
        await db_session.commit()

        fetched = await repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.phone_number == "0501234567"
        assert fetched.first_name == "John"
        assert fetched.last_name == "Doe"

    @pytest.mark.asyncio
    async def test_get_by_phone(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone_number="0509876543", first_name="Jane", last_name="", is_active=True, roles=[])
        await db_session.commit()

        found = await repo.get_by_phone("0509876543")
        assert found is not None
        assert found.first_name == "Jane"

        not_found = await repo.get_by_phone("0000000000")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_get_by_telegram_id(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone_number="0501111111", first_name="TG", last_name="User", is_active=True, roles=[])
        user.telegram_id = "123456789"
        await db_session.commit()

        found = await repo.get_by_telegram_id("123456789")
        assert found is not None
        assert found.phone_number == "0501111111"

    @pytest.mark.asyncio
    async def test_get_active_users(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone_number="0500000001", first_name="Active", last_name="", is_active=True, roles=[])
        await repo.create(phone_number="0500000002", first_name="Inactive", last_name="", is_active=False, roles=[])
        await db_session.commit()

        active = await repo.get_active_users()
        assert len(active) == 1
        assert active[0].first_name == "Active"

    @pytest.mark.asyncio
    async def test_get_active_users_is_deterministically_ordered(self, db_session: AsyncSession):
        """get_active_users must return a stable order (by last/first name).

        The __DEV_MODE__ auth bypass returns users[0]; with no ORDER BY that was an
        arbitrary DB-order row, so every guard could be authenticated as the same
        unrelated person. Pin the order so users[0] is at least predictable.
        """
        repo = UserRepository(db_session)
        # Inserted out of alphabetical order on purpose.
        await repo.create(phone_number="0500000010", first_name="Moshe", last_name="Shimon", is_active=True, roles=[])
        await repo.create(phone_number="0500000011", first_name="Bobby", last_name="Biton", is_active=True, roles=[])
        await repo.create(phone_number="0500000012", first_name="Avi", last_name="Aaron", is_active=True, roles=[])
        await db_session.commit()

        ordered = await repo.get_active_users()
        names = [(u.last_name, u.first_name) for u in ordered]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_link_telegram_id(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone_number="0502222222", first_name="Link", last_name="Me", is_active=True, roles=[])
        await db_session.commit()

        user = await repo.link_telegram_id_by_phone("0502222222", "999888777")
        assert user.telegram_id == "999888777"

    @pytest.mark.asyncio
    async def test_link_telegram_id_not_found(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        with pytest.raises(ValueError, match="No user found"):
            await repo.link_telegram_id_by_phone("0000000000", "123")

    @pytest.mark.asyncio
    async def test_deactivate_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone_number="0503333333", first_name="Deac", last_name="", is_active=True, roles=[])
        await db_session.commit()

        deactivated = await repo.deactivate_user(user.id)
        assert deactivated.is_active is False


# ──────────────── ScheduleWeekRepository ────────────────


class TestScheduleWeekRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db_session: AsyncSession):
        repo = ScheduleWeekRepository(db_session)
        week = await repo.create(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await db_session.commit()

        fetched = await repo.get_by_id(week.id)
        assert fetched is not None
        assert fetched.status == WeekStatus.OPEN

    @pytest.mark.asyncio
    async def test_get_current_open_week(self, db_session: AsyncSession):
        repo = ScheduleWeekRepository(db_session)
        await repo.create(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.LOCKED,
        )
        await repo.create(
            start_date=date(2026, 6, 8),
            end_date=date(2026, 6, 14),
            status=WeekStatus.OPEN,
        )
        await db_session.commit()

        open_week = await repo.get_current_open_week()
        assert open_week is not None
        assert open_week.start_date == date(2026, 6, 8)

    @pytest.mark.asyncio
    async def test_get_by_date_range(self, db_session: AsyncSession):
        repo = ScheduleWeekRepository(db_session)
        await repo.create(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await db_session.commit()

        found = await repo.get_by_date_range(date(2026, 6, 1), date(2026, 6, 7))
        assert found is not None

        not_found = await repo.get_by_date_range(date(2026, 1, 1), date(2026, 1, 7))
        assert not_found is None

    @pytest.mark.asyncio
    async def test_update_status(self, db_session: AsyncSession):
        repo = ScheduleWeekRepository(db_session)
        week = await repo.create(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await db_session.commit()

        updated = await repo.update_status(week.id, WeekStatus.LOCKED)
        assert updated.status == WeekStatus.LOCKED

    @pytest.mark.asyncio
    async def test_get_current_or_upcoming_week(self, db_session: AsyncSession):
        repo = ScheduleWeekRepository(db_session)
        # An already-ended week, the current (locked) week, and next week (closed).
        await repo.create(
            start_date=date(2026, 5, 25), end_date=date(2026, 5, 31),
            status=WeekStatus.LOCKED,
        )
        await repo.create(
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 7),
            status=WeekStatus.LOCKED,
        )
        await repo.create(
            start_date=date(2026, 6, 8), end_date=date(2026, 6, 14),
            status=WeekStatus.CLOSED,
        )
        await db_session.commit()

        # As of mid-current-week, the nearest not-yet-ended week is the locked one,
        # not next week's closed one.
        week = await repo.get_current_or_upcoming_week(date(2026, 6, 3))
        assert week is not None
        assert week.status == WeekStatus.LOCKED
        assert week.start_date == date(2026, 6, 1)

        # Once everything has ended, there is no current/upcoming week.
        none_week = await repo.get_current_or_upcoming_week(date(2027, 1, 1))
        assert none_week is None

    async def test_get_upcoming_unstarted_week(self, db_session: AsyncSession):
        repo = ScheduleWeekRepository(db_session)
        # The live (already-started) week and the upcoming (not-yet-started) one.
        await repo.create(
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 7),
            status=WeekStatus.LOCKED,
        )
        await repo.create(
            start_date=date(2026, 6, 8), end_date=date(2026, 6, 14),
            status=WeekStatus.CLOSED,
        )
        await repo.create(
            start_date=date(2026, 6, 15), end_date=date(2026, 6, 21),
            status=WeekStatus.CLOSED,
        )
        await db_session.commit()

        # Mid-current-week: the publish target is the nearest week that has NOT
        # started yet (the 6/8 closed one), never the live week nor a further-out one.
        week = await repo.get_upcoming_unstarted_week(date(2026, 6, 3))
        assert week is not None
        assert week.start_date == date(2026, 6, 8)

        # On the day a week starts it is no longer a publish target — the next
        # upcoming week wins.
        week = await repo.get_upcoming_unstarted_week(date(2026, 6, 8))
        assert week is not None
        assert week.start_date == date(2026, 6, 15)

        # When every week has already started, there is no upcoming week.
        none_week = await repo.get_upcoming_unstarted_week(date(2027, 1, 1))
        assert none_week is None


# ──────────────── SubmissionRepository ────────────────


class TestSubmissionRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get_submission(self, db_session: AsyncSession):
        user_repo = UserRepository(db_session)
        user = await user_repo.create(phone_number="0507777777", first_name="Sub", last_name="", is_active=True, roles=[])
        await db_session.commit()

        week_repo = ScheduleWeekRepository(db_session)
        week = await week_repo.create(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await db_session.commit()

        repo = SubmissionRepository(db_session)
        data = {
            "general_notes": "Available all week",
            "has_deviation": False,
            "daily_statuses": [
                {
                    "date": date(2026, 6, 1),
                    "is_available": True,
                    "shift_windows": [
                        {
                            "shift_type": ShiftType.MORNING,
                            "start_time": time(6, 0),
                            "end_time": time(14, 0),
                        }
                    ],
                },
                {
                    "date": date(2026, 6, 2),
                    "is_available": True,
                    "shift_windows": [
                        {
                            "shift_type": ShiftType.AFTERNOON,
                            "start_time": time(14, 0),
                            "end_time": time(22, 0),
                        }
                    ],
                },
            ],
        }
        submission = await repo.upsert_submission(user.id, week.id, data)
        await db_session.commit()

        assert submission.id is not None
        assert len(submission.daily_statuses) == 2

        # Fetch it back
        fetched = await repo.get_submission(user.id, week.id)
        assert fetched is not None
        assert fetched.general_notes == "Available all week"
        assert len(fetched.daily_statuses) == 2
        assert len(fetched.daily_statuses[0].shift_windows) == 1

    @pytest.mark.asyncio
    async def test_upsert_replaces_existing(self, db_session: AsyncSession):
        user_repo = UserRepository(db_session)
        user = await user_repo.create(phone_number="0508888888", first_name="Rep", last_name="", is_active=True, roles=[])
        await db_session.commit()

        week_repo = ScheduleWeekRepository(db_session)
        week = await week_repo.create(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await db_session.commit()

        repo = SubmissionRepository(db_session)

        # First submission
        data_v1 = {
            "general_notes": "v1",
            "has_deviation": False,
            "daily_statuses": [
                {
                    "date": date(2026, 6, 1),
                    "is_available": True,
                    "shift_windows": [],
                }
            ],
        }
        await repo.upsert_submission(user.id, week.id, data_v1)
        await db_session.commit()

        # Replace with v2
        data_v2 = {
            "general_notes": "v2",
            "has_deviation": True,
            "daily_statuses": [
                {
                    "date": date(2026, 6, 1),
                    "is_available": False,
                    "shift_windows": [],
                },
                {
                    "date": date(2026, 6, 2),
                    "is_available": True,
                    "shift_windows": [],
                },
            ],
        }
        submission = await repo.upsert_submission(user.id, week.id, data_v2)
        await db_session.commit()

        assert submission.general_notes == "v2"
        assert submission.has_deviation is True
        assert len(submission.daily_statuses) == 2

    @pytest.mark.asyncio
    async def test_get_missing_submissions(self, db_session: AsyncSession):
        user_repo = UserRepository(db_session)
        u1 = await user_repo.create(phone_number="0509000001", first_name="U1", last_name="", is_active=True, roles=[])
        u2 = await user_repo.create(phone_number="0509000002", first_name="U2", last_name="", is_active=True, roles=[])
        u3 = await user_repo.create(phone_number="0509000003", first_name="U3", last_name="", is_active=True, roles=[])
        await db_session.commit()

        week_repo = ScheduleWeekRepository(db_session)
        week = await week_repo.create(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await db_session.commit()

        repo = SubmissionRepository(db_session)
        # Only u1 submits
        data = {
            "general_notes": None,
            "has_deviation": False,
            "daily_statuses": [
                {"date": date(2026, 6, 1), "is_available": True, "shift_windows": []}
            ],
        }
        await repo.upsert_submission(u1.id, week.id, data)
        await db_session.commit()

        missing = await repo.get_missing_submissions(week.id, [u1.id, u2.id, u3.id])
        assert set(missing) == {u2.id, u3.id}


# ──────────────── AdminRepository ────────────────


class TestAdminRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_by_email(self, db_session: AsyncSession):
        repo = AdminRepository(db_session)
        admin = await repo.create_admin(
            email="admin@test.com",
            password_hash="hashed",
            full_name="Test Admin",
        )
        await db_session.commit()

        found = await repo.get_by_email("admin@test.com")
        assert found is not None
        assert found.full_name == "Test Admin"

    @pytest.mark.asyncio
    async def test_deactivate_admin(self, db_session: AsyncSession):
        repo = AdminRepository(db_session)
        admin = await repo.create_admin(
            email="deac@test.com",
            password_hash="hashed",
            full_name="Deac Admin",
        )
        await db_session.commit()

        deactivated = await repo.deactivate_admin(admin.id)
        assert deactivated.is_active is False


# ──────────────── SystemSettingsRepository ────────────────


class TestSystemSettingsRepository:
    @pytest.mark.asyncio
    async def test_set_and_get(self, db_session: AsyncSession):
        repo = SystemSettingsRepository(db_session)
        await repo.set("reminder_hour", "09:00", "Time to send reminders")
        await db_session.commit()

        value = await repo.get("reminder_hour")
        assert value == "09:00"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db_session: AsyncSession):
        repo = SystemSettingsRepository(db_session)
        value = await repo.get("nonexistent_key")
        assert value is None

    @pytest.mark.asyncio
    async def test_set_updates_existing(self, db_session: AsyncSession):
        repo = SystemSettingsRepository(db_session)
        await repo.set("test_key", "v1")
        await db_session.commit()

        await repo.set("test_key", "v2")
        await db_session.commit()

        value = await repo.get("test_key")
        assert value == "v2"

    @pytest.mark.asyncio
    async def test_delete(self, db_session: AsyncSession):
        repo = SystemSettingsRepository(db_session)
        await repo.set("to_delete", "bye")
        await db_session.commit()

        result = await repo.delete("to_delete")
        assert result is True

        value = await repo.get("to_delete")
        assert value is None

        # Delete non-existent
        result = await repo.delete("nonexistent")
        assert result is False