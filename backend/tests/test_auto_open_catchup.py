"""Tests for the resilient catch-up auto-open (feature: auto_open_resilient_catchup).

The scheduled auto-open cron fires once a week. If that single firing is missed
(deploy/restart, or a transient failure in the 00:00 rollover that leaves no week
for the 01:00 open to act on), ``WeekService.auto_open_if_due`` re-opens the
target week on the next weeks-list load / startup catch-up — but ONLY while we
are inside the configured weekly open window, and idempotently (it reuses
``auto_open_relevant_week``).
"""

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.week_service import WeekService
from app.utils.date_utils import week_range


def _week(status, start, end, opened_at=None):
    w = MagicMock()
    w.id = uuid.uuid4()
    w.status = status
    w.start_date = start
    w.end_date = end
    w.opened_at = opened_at  # fresh week by default (the no-reopen guard reads this)
    return w


# Auto-open Sunday 01:00, auto-lock Wednesday 12:00 — the live prod config.
OPEN_CFG = {"enabled": True, "weekday": "sun", "hour": 1, "minute": 0}
LOCK_CFG = {"enabled": True, "weekday": "wed", "hour": 12, "minute": 0}


# ── pure helpers: _last_weekly_moment ────────────────────────────────────────

def test_last_weekly_moment_today_after_time():
    now = datetime(2026, 6, 21, 5, 0)  # Sunday 05:00
    assert WeekService._last_weekly_moment(now, "sun", 1, 0) == datetime(2026, 6, 21, 1, 0)


def test_last_weekly_moment_today_before_time_steps_back_a_week():
    now = datetime(2026, 6, 21, 0, 30)  # Sunday 00:30, before the 01:00 open
    assert WeekService._last_weekly_moment(now, "sun", 1, 0) == datetime(2026, 6, 14, 1, 0)


def test_last_weekly_moment_other_weekday():
    now = datetime(2026, 6, 21, 5, 0)  # Sunday
    assert WeekService._last_weekly_moment(now, "wed", 12, 0) == datetime(2026, 6, 17, 12, 0)


# ── pure helpers: _is_in_open_phase ──────────────────────────────────────────

@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 6, 21, 5, 0), True),    # Sun 05:00 — the incident: after open, before next lock
        (datetime(2026, 6, 21, 0, 30), False),  # Sun 00:30 — this week's open hasn't fired yet
        (datetime(2026, 6, 23, 9, 0), True),    # Tue — between open and lock
        (datetime(2026, 6, 24, 13, 0), False),  # Wed 13:00 — just after the lock
        (datetime(2026, 6, 25, 9, 0), False),   # Thu — well after the lock
    ],
)
def test_is_in_open_phase(now, expected):
    assert WeekService._is_in_open_phase(now, OPEN_CFG, LOCK_CFG) is expected


def test_is_in_open_phase_disabled_open():
    disabled = {**OPEN_CFG, "enabled": False}
    assert WeekService._is_in_open_phase(datetime(2026, 6, 21, 5, 0), disabled, LOCK_CFG) is False


def test_is_in_open_phase_no_lock_stays_open():
    """With auto-lock disabled the week stays open until the Sunday rollover, so
    any moment after an auto-open counts as the open phase."""
    no_lock = {**LOCK_CFG, "enabled": False}
    assert WeekService._is_in_open_phase(datetime(2026, 6, 25, 9, 0), OPEN_CFG, no_lock) is True


# ── auto_open_if_due (mocked repo + patched settings) ────────────────────────

@pytest.mark.asyncio
async def test_auto_open_if_due_opens_when_in_phase():
    today = date.today()
    closed = _week(WeekStatus.CLOSED, today + timedelta(days=2), today + timedelta(days=8))

    repo = AsyncMock()
    repo.get_current_open_week.return_value = None
    repo.get_upcoming_closed_week.return_value = closed
    repo.get_by_id.return_value = closed
    repo.update.return_value = _week(WeekStatus.OPEN, closed.start_date, closed.end_date)

    user_repo = AsyncMock()
    user_repo.get_all.return_value = []  # no telegram recipients
    svc = WeekService(repo, user_repo)

    with patch(
        "app.services.settings_service.SettingsService.get_auto_open",
        new=AsyncMock(return_value=OPEN_CFG),
    ), patch(
        "app.services.settings_service.SettingsService.get_auto_lock",
        new=AsyncMock(return_value={**LOCK_CFG, "enabled": False}),
    ), patch.object(WeekService, "_is_in_open_phase", return_value=True):
        result = await svc.auto_open_if_due()

    # Opening a fresh week now also stamps opened_at, so assert on the call loosely.
    repo.update.assert_awaited_once()
    call_args, call_kwargs = repo.update.await_args
    assert call_args[0] == closed.id
    assert call_kwargs["status"] == WeekStatus.OPEN
    assert result is not None


@pytest.mark.asyncio
async def test_auto_open_if_due_noop_when_disabled():
    repo = AsyncMock()
    svc = WeekService(repo)

    with patch(
        "app.services.settings_service.SettingsService.get_auto_open",
        new=AsyncMock(return_value={**OPEN_CFG, "enabled": False}),
    ):
        result = await svc.auto_open_if_due()

    assert result is None
    repo.get_current_open_week.assert_not_awaited()
    repo.get_upcoming_closed_week.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_open_if_due_noop_when_not_in_phase():
    repo = AsyncMock()
    svc = WeekService(repo)

    with patch(
        "app.services.settings_service.SettingsService.get_auto_open",
        new=AsyncMock(return_value=OPEN_CFG),
    ), patch(
        "app.services.settings_service.SettingsService.get_auto_lock",
        new=AsyncMock(return_value=LOCK_CFG),
    ), patch.object(WeekService, "_is_in_open_phase", return_value=False):
        result = await svc.auto_open_if_due()

    assert result is None
    repo.get_current_open_week.assert_not_awaited()
    repo.get_upcoming_closed_week.assert_not_awaited()


# ── integration: auto_advance_weeks self-heals a missed open (real DB) ────────

@pytest.mark.asyncio
async def test_auto_advance_opens_upcoming_when_due(db_session):
    """The end-to-end gap that bit prod: the upcoming week exists but was never
    opened. With auto-open enabled (no auto-lock → always in the open phase), a
    weeks-list advance now opens it instead of leaving it closed."""
    settings_repo = SystemSettingsRepository(db_session)
    await settings_repo.set("auto_open_enabled", "true")
    await settings_repo.set("auto_open_weekday", "sunday")
    await settings_repo.set("auto_open_time", "01:00")
    # auto_lock left at its disabled default → in_open_phase is time-independent.
    await db_session.commit()

    today = date.today()
    ws, we = week_range(today)
    upcoming = ScheduleWeek(start_date=ws, end_date=we, status=WeekStatus.CLOSED)
    db_session.add(upcoming)
    await db_session.commit()

    svc = WeekService(ScheduleWeekRepository(db_session))  # no user_repo → no broadcast
    await svc.auto_advance_weeks()

    await db_session.refresh(upcoming)
    assert upcoming.status == WeekStatus.OPEN
    assert upcoming.opened_at is not None


@pytest.mark.asyncio
async def test_auto_advance_leaves_closed_when_auto_open_disabled(db_session):
    """Guard: with auto-open disabled the advance must NOT open the week — the
    manual/cron behavior is unchanged for admins who don't use automation."""
    settings_repo = SystemSettingsRepository(db_session)
    await settings_repo.set("auto_open_enabled", "false")
    await db_session.commit()

    today = date.today()
    ws, we = week_range(today)
    upcoming = ScheduleWeek(start_date=ws, end_date=we, status=WeekStatus.CLOSED)
    db_session.add(upcoming)
    await db_session.commit()

    svc = WeekService(ScheduleWeekRepository(db_session))
    await svc.auto_advance_weeks()

    await db_session.refresh(upcoming)
    assert upcoming.status == WeekStatus.CLOSED
