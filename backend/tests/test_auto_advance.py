"""Tests for the automatic Saturday-night (Motzaei Shabbat) week rollover.

The rollover (``WeekService.auto_advance_weeks``) is idempotent and self-healing:
  1. Any OPEN week whose ``start_date`` has arrived is auto-locked (silently —
     no Telegram broadcast at midnight). It is no longer a submission target.
  2. The upcoming Sun–Sat week is ensured CLOSED (existing ``auto_rotate_weeks``)
     so the admin always has a next week ready to open.

A week that was already locked/published, or an OPEN *future* week, is untouched.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.constants import WeekStatus
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.services.week_service import WeekService
from app.utils.date_utils import upcoming_sunday, week_range


def _week(status, start, end):
    w = MagicMock()
    w.id = uuid.uuid4()
    w.status = status
    w.start_date = start
    w.end_date = end
    return w


# ── Service-level (mocked repo) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lock_expired_open_weeks_locks_silently():
    """An open week whose start_date arrived is locked WITHOUT notifying guards."""
    today = date.today()
    stale = _week(WeekStatus.OPEN, today - timedelta(days=1), today + timedelta(days=5))

    repo = AsyncMock()
    repo.get_weeks_to_finalize_on_or_before.return_value = [stale]
    repo.get_by_id.return_value = stale
    repo.update.return_value = _week(WeekStatus.LOCKED, stale.start_date, stale.end_date)

    user_repo = AsyncMock()
    svc = WeekService(repo, user_repo)
    await svc.lock_expired_open_weeks()

    # Transitioned to LOCKED…
    repo.update.assert_awaited_once_with(stale.id, status=WeekStatus.LOCKED)
    # …and NO Telegram broadcast happened (user list is only fetched to notify).
    user_repo.get_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_lock_expired_open_weeks_noop_when_none():
    """No stale open week → nothing is locked."""
    repo = AsyncMock()
    repo.get_weeks_to_finalize_on_or_before.return_value = []

    svc = WeekService(repo)
    await svc.lock_expired_open_weeks()

    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_advance_locks_and_creates_next():
    """auto_advance both locks the stale open week and ensures the upcoming week."""
    today = date.today()
    ws, we = week_range(today)
    stale = _week(WeekStatus.OPEN, today - timedelta(days=1), today + timedelta(days=5))

    repo = AsyncMock()
    repo.get_weeks_to_finalize_on_or_before.return_value = [stale]
    repo.get_by_id.return_value = stale
    repo.update.return_value = _week(WeekStatus.LOCKED, stale.start_date, stale.end_date)
    repo.get_by_date_range.return_value = None  # upcoming week missing
    repo.save.return_value = _week(WeekStatus.CLOSED, ws, we)
    repo.get_weeks_beyond_retention.return_value = []  # nothing to purge

    svc = WeekService(repo)
    await svc.auto_advance_weeks()

    repo.update.assert_awaited_once_with(stale.id, status=WeekStatus.LOCKED)  # locked
    repo.save.assert_awaited_once()  # upcoming created
    assert repo.save.call_args.args[0].status == WeekStatus.CLOSED


# ── Repository-level (real in-memory DB) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_repo_returns_started_weeks_to_finalize(db_session):
    """Finalize-query returns EVERY started, not-yet-locked week — OPEN, CLOSED
    that already ran, and CLOSED that was never opened — but NOT future weeks."""
    from datetime import datetime

    from app.models.schedule_week import ScheduleWeek

    today = date.today()
    open_started = ScheduleWeek(
        start_date=today - timedelta(days=2),
        end_date=today + timedelta(days=4),
        status=WeekStatus.OPEN,
    )
    # A future week — must not be finalized because it hasn't started. CLOSED (not
    # OPEN) to respect the single-open invariant; the finalize query keys on
    # start_date regardless of status, so this still proves "future → not finalized".
    future_week = ScheduleWeek(
        start_date=today + timedelta(days=5),
        end_date=today + timedelta(days=11),
        status=WeekStatus.CLOSED,
        opened_at=None,
    )
    closed_started_opened = ScheduleWeek(
        start_date=today - timedelta(days=9),
        end_date=today - timedelta(days=3),
        status=WeekStatus.CLOSED,
        opened_at=datetime(2026, 1, 1, 12, 0, 0),  # had its submission window
    )
    # A never-opened CLOSED week that already started is a stale ghost — it must
    # now be finalized too, so its editing UI can't stay live forever.
    closed_started_never_opened = ScheduleWeek(
        start_date=today,  # distinct range (unique date-range constraint, B-4)
        end_date=today + timedelta(days=6),
        status=WeekStatus.CLOSED,
        opened_at=None,
    )
    db_session.add_all(
        [open_started, future_week, closed_started_opened, closed_started_never_opened]
    )
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    result = await repo.get_weeks_to_finalize_on_or_before(today)

    ids = {w.id for w in result}
    assert open_started.id in ids
    assert closed_started_opened.id in ids  # already opened → finalize
    assert closed_started_never_opened.id in ids  # started ghost → finalize too
    assert future_week.id not in ids  # not started yet → keep


@pytest.mark.asyncio
async def test_rollover_finalizes_started_weeks_keeps_future(db_session):
    """End-to-end rollover: every started week is finalized to LOCKED — including
    a never-opened one that already started — while a FUTURE never-opened week
    stays CLOSED (the only week the rollover must not disturb)."""
    from datetime import datetime

    from app.models.schedule_week import ScheduleWeek

    today = date.today()
    prev_cycle = ScheduleWeek(
        start_date=today - timedelta(days=7),
        end_date=today - timedelta(days=1),
        status=WeekStatus.CLOSED,
        opened_at=datetime(2026, 1, 1, 12, 0, 0),  # had its submission window
    )
    started_never_opened = ScheduleWeek(
        start_date=today,
        end_date=today + timedelta(days=6),
        status=WeekStatus.CLOSED,
        opened_at=None,  # never opened but already started → stale ghost
    )
    future = ScheduleWeek(
        start_date=today + timedelta(days=7),
        end_date=today + timedelta(days=13),
        status=WeekStatus.CLOSED,
        opened_at=None,  # the real upcoming target — must be left alone
    )
    db_session.add_all([prev_cycle, started_never_opened, future])
    await db_session.commit()

    svc = WeekService(ScheduleWeekRepository(db_session))
    await svc.lock_expired_open_weeks()

    await db_session.refresh(prev_cycle)
    await db_session.refresh(started_never_opened)
    await db_session.refresh(future)
    assert prev_cycle.status == WeekStatus.LOCKED  # finalized
    assert started_never_opened.status == WeekStatus.LOCKED  # ghost finalized too
    assert future.status == WeekStatus.CLOSED  # future target untouched


# ── Full flow (service + real DB) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_rollover_locks_open_and_creates_upcoming(db_session):
    """End-to-end: a started open week is locked; a future (CLOSED) week is left
    untouched; the upcoming CLOSED week is created.

    Note: under the single-open invariant there can be at most one OPEN week, so
    the "future week" is CLOSED here — the rollover must still not disturb it."""
    from app.models.schedule_week import ScheduleWeek

    today = date.today()
    # Open week whose start_date has arrived → must be locked.
    started_open = ScheduleWeek(
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=5),
        status=WeekStatus.OPEN,
    )
    # A future CLOSED week → must stay CLOSED (the rollover only touches started weeks).
    far_start = upcoming_sunday(today) + timedelta(days=14)
    future_closed = ScheduleWeek(
        start_date=far_start,
        end_date=far_start + timedelta(days=6),
        status=WeekStatus.CLOSED,
    )
    db_session.add_all([started_open, future_closed])
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    svc = WeekService(repo)  # no user_repo → no notifications regardless
    await svc.auto_advance_weeks()

    await db_session.refresh(started_open)
    await db_session.refresh(future_closed)
    assert started_open.status == WeekStatus.LOCKED
    assert future_closed.status == WeekStatus.CLOSED

    # Upcoming Sun–Sat week now exists as CLOSED.
    ws, we = week_range(today)
    upcoming = await repo.get_by_date_range(ws, we)
    assert upcoming is not None
    assert upcoming.status == WeekStatus.CLOSED


# ── Timezone boundary: Sat-21:00-UTC == Sun-00:00-IL (B-3) ───────────────────
#
# On a UTC container a naive today() still reads Saturday at the Sunday rollover,
# so the cron used to no-op and the week neither locked nor rolled. These pin the
# behaviour to the *Israeli* date by patching today_il — the whole reason the
# helper is a single source: it can be patched in one place. Patch the symbol as
# imported into week_service, not date_utils, or the patch won't take.

@pytest.mark.asyncio
async def test_rollover_at_saturday_2100_utc_locks_and_creates_next(db_session):
    """At Sat-21:00-UTC (= Sun-00:00-IL) the just-started week locks and the next
    week is created — the rollover fires on the Israeli date, not the UTC one."""
    from app.models.schedule_week import ScheduleWeek

    sunday = date(2026, 7, 5)  # a Sunday — the Israeli date at the rollover instant
    started_open = ScheduleWeek(
        start_date=sunday,
        end_date=sunday + timedelta(days=6),
        status=WeekStatus.OPEN,
    )
    db_session.add(started_open)
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    svc = WeekService(repo)
    with patch("app.services.week_service.today_il", return_value=sunday):
        await svc.auto_advance_weeks()

    await db_session.refresh(started_open)
    assert started_open.status == WeekStatus.LOCKED  # its start_date has arrived

    ws, we = week_range(sunday)  # next Sun–Sat
    upcoming = await repo.get_by_date_range(ws, we)
    assert upcoming is not None
    assert upcoming.status == WeekStatus.CLOSED


@pytest.mark.asyncio
async def test_rollover_is_idempotent(db_session):
    """A second rollover at the same instant creates no duplicate week and changes
    no statuses (guards the self-heal that runs on every request)."""
    from app.models.schedule_week import ScheduleWeek

    sunday = date(2026, 7, 5)
    started_open = ScheduleWeek(
        start_date=sunday,
        end_date=sunday + timedelta(days=6),
        status=WeekStatus.OPEN,
    )
    db_session.add(started_open)
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    svc = WeekService(repo)
    with patch("app.services.week_service.today_il", return_value=sunday):
        await svc.auto_advance_weeks()
        await svc.auto_advance_weeks()  # second run, same instant

    all_weeks = await repo.get_all()
    # Exactly two weeks: the locked current + the single upcoming CLOSED one.
    assert len(all_weeks) == 2
    ws, we = week_range(sunday)
    upcoming = [w for w in all_weeks if (w.start_date, w.end_date) == (ws, we)]
    assert len(upcoming) == 1  # not duplicated
    assert upcoming[0].status == WeekStatus.CLOSED
