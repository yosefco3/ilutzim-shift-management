"""
Tests for all SQLAlchemy models — table names, columns, and basic creation.
"""

import uuid
from datetime import date, time

import pytest
from sqlalchemy import inspect

from app.constants import AdminRole, ShiftType, UserRole, WeekStatus
from app.models import (
    Admin,
    DailyStatus,
    ScheduleWeek,
    ShiftWindow,
    SystemSetting,
    User,
    WeeklySubmission,
)

# ── helpers ──────────────────────────────────────────────────────────────


async def _persist(db_session, *instances):
    """Add, flush, and return instances from the DB."""
    for obj in instances:
        db_session.add(obj)
    await db_session.flush()
    return instances if len(instances) > 1 else instances[0]


# ── User ─────────────────────────────────────────────────────────────────


class TestUserModel:
    async def test_create_user(self, db_session):
        user = User(
            phone_number="0501234567",
            telegram_id="123456789",
            first_name="John",
            last_name="Doe",
            roles=["AHMASH"],
            is_active=True,
        )
        await _persist(db_session, user)
        assert user.id is not None
        assert user.phone_number == "0501234567"
        assert user.roles == ["AHMASH"]
        assert user.created_at is not None

    async def test_user_table_name(self):
        assert User.__tablename__ == "users"

    async def test_user_unique_phone(self, db_session):
        u1 = User(phone_number="0509999999", first_name="A", last_name="", roles=[])
        u2 = User(phone_number="0509999999", first_name="B", last_name="", roles=[])
        db_session.add(u1)
        await db_session.flush()
        db_session.add(u2)
        with pytest.raises(Exception):
            await db_session.flush()


# ── ScheduleWeek ─────────────────────────────────────────────────────────


class TestScheduleWeekModel:
    async def test_create_schedule_week(self, db_session):
        sw = ScheduleWeek(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await _persist(db_session, sw)
        assert sw.id is not None
        assert sw.start_date == date(2026, 6, 1)
        assert sw.status == WeekStatus.OPEN

    async def test_schedule_week_table_name(self):
        assert ScheduleWeek.__tablename__ == "schedule_weeks"


# ── WeeklySubmission ─────────────────────────────────────────────────────


class TestWeeklySubmissionModel:
    async def test_create_weekly_submission(self, db_session):
        user = User(phone_number="0502222222", first_name="Guard", last_name="B", roles=[])
        sw = ScheduleWeek(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await _persist(db_session, user, sw)
        sub = WeeklySubmission(
            user_id=user.id,
            week_id=sw.id,
        )
        await _persist(db_session, sub)
        assert sub.id is not None

    async def test_weekly_submission_table_name(self):
        assert WeeklySubmission.__tablename__ == "weekly_submissions"


# ── DailyStatus ──────────────────────────────────────────────────────────


class TestDailyStatusModel:
    async def test_create_daily_status(self, db_session):
        user = User(phone_number="0503333333", first_name="Guard", last_name="C", roles=[])
        sw = ScheduleWeek(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await _persist(db_session, user, sw)
        sub = WeeklySubmission(user_id=user.id, week_id=sw.id)
        await _persist(db_session, sub)
        ds = DailyStatus(submission_id=sub.id, date=date(2026, 6, 1), is_available=True)
        await _persist(db_session, ds)
        assert ds.id is not None
        assert ds.is_available is True

    async def test_daily_status_table_name(self):
        assert DailyStatus.__tablename__ == "daily_statuses"


# ── ShiftWindow ──────────────────────────────────────────────────────────


class TestShiftWindowModel:
    async def test_create_shift_window(self, db_session):
        user = User(phone_number="0504444444", first_name="Guard", last_name="D", roles=[])
        sw = ScheduleWeek(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=WeekStatus.OPEN,
        )
        await _persist(db_session, user, sw)
        sub = WeeklySubmission(user_id=user.id, week_id=sw.id)
        await _persist(db_session, sub)
        ds = DailyStatus(submission_id=sub.id, date=date(2026, 6, 1), is_available=True)
        await _persist(db_session, ds)
        win = ShiftWindow(
            daily_status_id=ds.id,
            shift_type=ShiftType.MORNING,
            start_time=time(6, 0),
            end_time=time(14, 0),
        )
        await _persist(db_session, win)
        assert win.id is not None
        assert win.shift_type == ShiftType.MORNING

    async def test_shift_window_table_name(self):
        assert ShiftWindow.__tablename__ == "shift_windows"


# ── Admin ────────────────────────────────────────────────────────────────


class TestAdminModel:
    async def test_create_admin(self, db_session):
        admin = Admin(
            email="admin@test.com",
            password_hash="hashed",
            full_name="Admin User",
            role=AdminRole.SUPER_ADMIN,
        )
        await _persist(db_session, admin)
        assert admin.id is not None

    async def test_admin_table_name(self):
        assert Admin.__tablename__ == "admins"


# ── SystemSetting ────────────────────────────────────────────────────────


class TestSystemSettingModel:
    async def test_create_system_setting(self, db_session):
        s = SystemSetting(
            setting_key="deadline_hour",
            setting_value="18",
            description="Submission deadline hour",
        )
        await _persist(db_session, s)
        assert s.setting_key == "deadline_hour"

    async def test_system_setting_table_name(self):
        assert SystemSetting.__tablename__ == "system_settings"


# ── Table introspection ──────────────────────────────────────────────────


class TestTablesExist:
    async def test_all_tables_created(self, db_session):
        from sqlalchemy import text
        result = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        table_names = {row[0] for row in result}
        expected = {
            "users",
            "schedule_weeks",
            "weekly_submissions",
            "daily_statuses",
            "shift_windows",
            "admins",
            "system_settings",
        }
        assert expected.issubset(
            table_names
        ), f"Missing tables: {expected - table_names}"
