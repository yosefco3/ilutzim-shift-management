"""Tests for the resilient catch-up auto-lock (mirror of auto_open_resilient_catchup).

The scheduled auto-lock cron fires once a week. If that single firing is missed
(server down at the lock time, deploy/restart), the week stays OPEN past its lock
time — the Sunday-rollover self-heal only finalizes weeks whose ``start_date`` has
arrived, not a lock TIME earlier in the same cycle. ``WeekService.auto_lock_if_due``
closes the open week on the next weeks-list load / startup catch-up, but ONLY while
we are inside the configured weekly lock window, and idempotently (it reuses
``auto_lock_open_week``).
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.week_service import WeekService
from app.utils.date_utils import week_range


def _week(status, start, end):
    w = MagicMock()
    w.id = uuid.uuid4()
    w.status = status
    w.start_date = start
    w.end_date = end
    return w


# Auto-open Sunday 01:00, auto-lock Wednesday 12:00 — the live prod config.
OPEN_CFG = {"enabled": True, "weekday": "sun", "hour": 1, "minute": 0}
LOCK_CFG = {"enabled": True, "weekday": "wed", "hour": 12, "minute": 0}


# ── pure helper: _is_in_lock_phase (exact complement of _is_in_open_phase) ────

@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 6, 21, 5, 0), False),   # Sun 05:00 — after open, before next lock
        (datetime(2026, 6, 21, 0, 30), True),   # Sun 00:30 — this week's open hasn't fired yet
        (datetime(2026, 6, 23, 9, 0), False),   # Tue — between open and lock
        (datetime(2026, 6, 24, 13, 0), True),   # Wed 13:00 — just after the lock (the incident)
        (datetime(2026, 6, 25, 9, 0), True),    # Thu — well after the lock, still stuck open
    ],
)
def test_is_in_lock_phase(now, expected):
    assert WeekService._is_in_lock_phase(now, OPEN_CFG, LOCK_CFG) is expected


def test_is_in_lock_phase_is_complement_of_open_phase():
    """Whenever both automations are enabled the two phases partition time."""
    for day in range(7):
        for hour in (0, 5, 12, 13, 20):
            now = datetime(2026, 6, 21) + timedelta(days=day, hours=hour)
            in_open = WeekService._is_in_open_phase(now, OPEN_CFG, LOCK_CFG)
            in_lock = WeekService._is_in_lock_phase(now, OPEN_CFG, LOCK_CFG)
            assert in_open is not in_lock, now


def test_is_in_lock_phase_disabled_lock():
    disabled = {**LOCK_CFG, "enabled": False}
    assert WeekService._is_in_lock_phase(datetime(2026, 6, 24, 13, 0), OPEN_CFG, disabled) is False


def test_is_in_lock_phase_requires_auto_open():
    """Without a recurring auto-open boundary the lock window is unbounded on the
    left, so a catch-up can't be scoped safely — it must not fire."""
    no_open = {**OPEN_CFG, "enabled": False}
    assert WeekService._is_in_lock_phase(datetime(2026, 6, 24, 13, 0), no_open, LOCK_CFG) is False


# ── auto_lock_if_due (mocked repo + patched settings) ────────────────────────

@pytest.mark.asyncio
async def test_auto_lock_if_due_closes_when_in_phase():
    today = date.today()
    open_week = _week(WeekStatus.OPEN, today, today + timedelta(days=6))

    repo = AsyncMock()
    repo.get_current_open_week.return_value = open_week
    repo.get_by_id.return_value = open_week
    repo.update.return_value = _week(WeekStatus.CLOSED, open_week.start_date, open_week.end_date)

    user_repo = AsyncMock()
    user_repo.get_all.return_value = []  # no telegram recipients
    svc = WeekService(repo, user_repo)

    with patch(
        "app.services.settings_service.SettingsService.get_auto_open",
        new=AsyncMock(return_value=OPEN_CFG),
    ), patch(
        "app.services.settings_service.SettingsService.get_auto_lock",
        new=AsyncMock(return_value=LOCK_CFG),
    ), patch.object(WeekService, "_is_in_lock_phase", return_value=True):
        result = await svc.auto_lock_if_due()

    repo.update.assert_awaited_once_with(open_week.id, status=WeekStatus.CLOSED)
    assert result is not None


@pytest.mark.asyncio
async def test_auto_lock_if_due_noop_when_disabled():
    repo = AsyncMock()
    svc = WeekService(repo)

    with patch(
        "app.services.settings_service.SettingsService.get_auto_lock",
        new=AsyncMock(return_value={**LOCK_CFG, "enabled": False}),
    ):
        result = await svc.auto_lock_if_due()

    assert result is None
    repo.get_current_open_week.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_lock_if_due_noop_when_not_in_phase():
    repo = AsyncMock()
    svc = WeekService(repo)

    with patch(
        "app.services.settings_service.SettingsService.get_auto_open",
        new=AsyncMock(return_value=OPEN_CFG),
    ), patch(
        "app.services.settings_service.SettingsService.get_auto_lock",
        new=AsyncMock(return_value=LOCK_CFG),
    ), patch.object(WeekService, "_is_in_lock_phase", return_value=False):
        result = await svc.auto_lock_if_due()

    assert result is None
    repo.get_current_open_week.assert_not_awaited()


# ── integration: auto_advance_weeks self-heals a missed lock (real DB) ────────

@pytest.mark.asyncio
async def test_auto_advance_closes_open_week_when_lock_passed(db_session):
    """The incident: the lock time passed while the server was down, so the week
    is still OPEN. A weeks-list advance now closes its submission window."""
    settings_repo = SystemSettingsRepository(db_session)
    await settings_repo.set("auto_open_enabled", "true")
    await settings_repo.set("auto_open_weekday", "sunday")
    await settings_repo.set("auto_open_time", "01:00")
    await settings_repo.set("auto_lock_enabled", "true")
    await settings_repo.set("auto_lock_weekday", "wednesday")
    await settings_repo.set("auto_lock_time", "12:00")
    await db_session.commit()

    today = date.today()
    ws, we = week_range(today + timedelta(days=7))  # an upcoming (not-yet-started) week
    stuck = ScheduleWeek(
        start_date=ws,
        end_date=we,
        status=WeekStatus.OPEN,
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db_session.add(stuck)
    await db_session.commit()

    svc = WeekService(ScheduleWeekRepository(db_session))  # no user_repo → no broadcast

    # Force "now" into the lock phase regardless of the real weekday the test runs.
    with patch.object(WeekService, "_is_in_lock_phase", return_value=True), patch.object(
        WeekService, "_is_in_open_phase", return_value=False
    ):
        await svc.auto_advance_weeks()

    await db_session.refresh(stuck)
    assert stuck.status == WeekStatus.CLOSED


@pytest.mark.asyncio
async def test_auto_advance_leaves_open_when_auto_lock_disabled(db_session):
    """Guard: with auto-lock disabled the advance must NOT close the week."""
    settings_repo = SystemSettingsRepository(db_session)
    await settings_repo.set("auto_open_enabled", "true")
    await settings_repo.set("auto_open_weekday", "sunday")
    await settings_repo.set("auto_open_time", "01:00")
    await settings_repo.set("auto_lock_enabled", "false")
    await db_session.commit()

    today = date.today()
    ws, we = week_range(today + timedelta(days=7))
    stuck = ScheduleWeek(
        start_date=ws,
        end_date=we,
        status=WeekStatus.OPEN,
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db_session.add(stuck)
    await db_session.commit()

    svc = WeekService(ScheduleWeekRepository(db_session))
    await svc.auto_advance_weeks()

    await db_session.refresh(stuck)
    assert stuck.status == WeekStatus.OPEN
