"""Tests for the cron entry points WeekService.auto_open_relevant_week and
auto_lock_open_week (prompt 06).

Auto-open: closed → open, broadcasts to guards, idempotent (skips if a week is
already open or there is no closed candidate). Auto-lock: open → closed,
broadcasts the lock notice to guards, idempotent, never touches published weeks.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.constants import WeekStatus
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.services.week_service import WeekService


def _week(status, start, end, opened_at=None):
    w = MagicMock()
    w.id = uuid.uuid4()
    w.status = status
    w.start_date = start
    w.end_date = end
    w.opened_at = opened_at  # fresh week by default (the no-reopen guard reads this)
    return w


# ── auto_open (mocked repo) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_open_opens_upcoming_closed_week():
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
    result = await svc.auto_open_relevant_week()

    # Opening a fresh week also stamps opened_at, so assert on the call loosely.
    repo.update.assert_awaited_once()
    call_args, call_kwargs = repo.update.await_args
    assert call_args[0] == closed.id
    assert call_kwargs["status"] == WeekStatus.OPEN
    user_repo.get_all.assert_awaited()  # notify=True path attempted the broadcast
    assert result is not None


@pytest.mark.asyncio
async def test_auto_open_noop_when_already_open():
    today = date.today()
    repo = AsyncMock()
    repo.get_current_open_week.return_value = _week(
        WeekStatus.OPEN, today, today + timedelta(days=6)
    )

    svc = WeekService(repo, AsyncMock())
    result = await svc.auto_open_relevant_week()

    assert result is None
    repo.update.assert_not_awaited()
    repo.get_upcoming_closed_week.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_open_noop_when_no_candidate():
    repo = AsyncMock()
    repo.get_current_open_week.return_value = None
    repo.get_upcoming_closed_week.return_value = None

    svc = WeekService(repo, AsyncMock())
    result = await svc.auto_open_relevant_week()

    assert result is None
    repo.update.assert_not_awaited()


# ── auto_lock (mocked repo) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_lock_locks_open_week_and_notifies():
    today = date.today()
    open_week = _week(WeekStatus.OPEN, today, today + timedelta(days=6))

    repo = AsyncMock()
    repo.get_current_open_week.return_value = open_week
    repo.get_by_id.return_value = open_week
    repo.update.return_value = _week(WeekStatus.CLOSED, open_week.start_date, open_week.end_date)

    user_repo = AsyncMock()
    user_repo.get_all.return_value = []  # no telegram recipients
    svc = WeekService(repo, user_repo)
    result = await svc.auto_lock_open_week()

    # auto-lock TIME closes the submission window (reopenable), it does not finalize.
    repo.update.assert_awaited_once_with(open_week.id, status=WeekStatus.CLOSED)
    user_repo.get_all.assert_awaited()  # broadcasts the lock notice to guards
    assert result is not None


@pytest.mark.asyncio
async def test_auto_lock_noop_when_no_open_week():
    repo = AsyncMock()
    repo.get_current_open_week.return_value = None

    svc = WeekService(repo, AsyncMock())
    result = await svc.auto_lock_open_week()

    assert result is None
    repo.update.assert_not_awaited()


# ── repo-level (real in-memory DB) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_upcoming_closed_week_picks_nearest(db_session):
    from app.models.schedule_week import ScheduleWeek

    today = date.today()
    near = ScheduleWeek(
        start_date=today + timedelta(days=2),
        end_date=today + timedelta(days=8),
        status=WeekStatus.CLOSED,
    )
    far = ScheduleWeek(
        start_date=today + timedelta(days=9),
        end_date=today + timedelta(days=15),
        status=WeekStatus.CLOSED,
    )
    ended = ScheduleWeek(
        start_date=today - timedelta(days=10),
        end_date=today - timedelta(days=4),
        status=WeekStatus.CLOSED,
    )
    opened = ScheduleWeek(
        start_date=today,
        end_date=today + timedelta(days=6),
        status=WeekStatus.OPEN,
    )
    db_session.add_all([near, far, ended, opened])
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    result = await repo.get_upcoming_closed_week(today)
    assert result is not None
    assert result.id == near.id  # nearest non-ended CLOSED week


@pytest.mark.asyncio
async def test_get_upcoming_closed_week_skips_already_opened(db_session):
    """Anti-loop: a CLOSED week that already had its submission window
    (opened_at set) must NOT be returned — otherwise the auto-open cron would
    re-open a week it just closed, forever."""
    from datetime import datetime

    from app.models.schedule_week import ScheduleWeek

    today = date.today()
    reopened_candidate = ScheduleWeek(
        start_date=today + timedelta(days=1),
        end_date=today + timedelta(days=7),
        status=WeekStatus.CLOSED,
        opened_at=datetime(2026, 1, 1, 12, 0, 0),  # already opened once
    )
    fresh = ScheduleWeek(
        start_date=today + timedelta(days=2),
        end_date=today + timedelta(days=8),
        status=WeekStatus.CLOSED,
        opened_at=None,  # never opened
    )
    db_session.add_all([reopened_candidate, fresh])
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    result = await repo.get_upcoming_closed_week(today)
    assert result is not None
    assert result.id == fresh.id  # the never-opened week, not the closer-but-opened one


# ── full flow (service + real DB) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_lock_does_not_touch_published(db_session):
    from app.models.schedule_week import ScheduleWeek

    today = date.today()
    published = ScheduleWeek(
        start_date=today,
        end_date=today + timedelta(days=6),
        status=WeekStatus.LOCKED,
    )
    db_session.add(published)
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    svc = WeekService(repo)
    result = await svc.auto_lock_open_week()  # no OPEN week exists

    assert result is None
    await db_session.refresh(published)
    assert published.status == WeekStatus.LOCKED


@pytest.mark.asyncio
async def test_auto_open_then_lock_full_cycle(db_session):
    from app.models.schedule_week import ScheduleWeek

    today = date.today()
    closed = ScheduleWeek(
        start_date=today + timedelta(days=2),
        end_date=today + timedelta(days=8),
        status=WeekStatus.CLOSED,
    )
    db_session.add(closed)
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    svc = WeekService(repo)  # no user_repo → no broadcast regardless

    opened = await svc.auto_open_relevant_week()
    assert opened is not None
    await db_session.refresh(closed)
    assert closed.status == WeekStatus.OPEN

    # second call is idempotent — already open, no second open
    assert await svc.auto_open_relevant_week() is None

    closed_again = await svc.auto_lock_open_week()
    assert closed_again is not None
    await db_session.refresh(closed)
    # auto-lock TIME returns the week to CLOSED (reopenable), not LOCKED.
    assert closed.status == WeekStatus.CLOSED
    assert closed.opened_at is not None  # but it remembers it was opened

    # idempotent — nothing OPEN now
    assert await svc.auto_lock_open_week() is None

    # anti-loop: the auto-open cron must NOT re-open this already-opened week
    assert await svc.auto_open_relevant_week() is None
