"""Tests for the data-retention purge.

The app keeps only the most recent ``RETENTION_WEEKS`` weeks (by ``start_date``).
``WeekService.purge_old_weeks`` hard-deletes everything older — including
published weeks — and the DB-level ``ON DELETE CASCADE`` chain removes each
purged week's submissions, daily statuses, and shift windows.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.constants import UserRole, WeekStatus
from app.models.daily_status import DailyStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.models.weekly_submission import WeeklySubmission
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.services.week_service import WeekService

pytestmark = pytest.mark.asyncio


async def _make_weeks(db_session, count, *, status=WeekStatus.LOCKED):
    """Create ``count`` weeks with descending start_date (week 0 = newest)."""
    base = date(2026, 1, 4)  # a Sunday
    weeks = []
    for i in range(count):
        start = base - timedelta(weeks=i)
        weeks.append(
            ScheduleWeek(start_date=start, end_date=start + timedelta(days=6), status=status)
        )
    db_session.add_all(weeks)
    await db_session.commit()
    for w in weeks:
        await db_session.refresh(w)
    return weeks  # index 0 = newest


# ── Repository ────────────────────────────────────────────────────────────


async def test_repo_returns_only_weeks_beyond_keep(db_session):
    """get_weeks_beyond_retention returns every week past the newest ``keep``."""
    await _make_weeks(db_session, 5)
    repo = ScheduleWeekRepository(db_session)

    stale = await repo.get_weeks_beyond_retention(3)

    assert len(stale) == 2  # 5 total − 3 kept
    # The two returned are the oldest (smallest start_date).
    starts = sorted(w.start_date for w in stale)
    assert starts[0] < starts[1]


async def test_repo_keep_zero_or_negative_returns_empty(db_session):
    """A non-positive keep never purges everything (safety guard)."""
    await _make_weeks(db_session, 3)
    repo = ScheduleWeekRepository(db_session)

    assert await repo.get_weeks_beyond_retention(0) == []
    assert await repo.get_weeks_beyond_retention(-5) == []


async def test_repo_fewer_than_keep_returns_empty(db_session):
    """With ≤ keep weeks, nothing is beyond retention."""
    await _make_weeks(db_session, 3)
    repo = ScheduleWeekRepository(db_session)

    assert await repo.get_weeks_beyond_retention(60) == []


# ── Service ───────────────────────────────────────────────────────────────


async def test_purge_keeps_only_retention_weeks(db_session, monkeypatch):
    """purge_old_weeks leaves exactly RETENTION_WEEKS rows, dropping the oldest."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "RETENTION_WEEKS", 60)
    monkeypatch.setattr(settings, "RETENTION_ENABLED", True)

    weeks = await _make_weeks(db_session, 63)
    oldest_ids = {w.id for w in sorted(weeks, key=lambda w: w.start_date)[:3]}

    repo = ScheduleWeekRepository(db_session)
    svc = WeekService(repo)
    purged = await svc.purge_old_weeks()

    assert purged == 3
    remaining = await db_session.scalar(select(func.count()).select_from(ScheduleWeek))
    assert remaining == 60
    # The three oldest are gone.
    rows = (await db_session.execute(select(ScheduleWeek.id))).scalars().all()
    assert oldest_ids.isdisjoint(set(rows))


async def test_purge_deletes_published_weeks(db_session, monkeypatch):
    """Old published weeks ARE purged (retention overrides the history guard)."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "RETENTION_WEEKS", 2)
    monkeypatch.setattr(settings, "RETENTION_ENABLED", True)

    await _make_weeks(db_session, 4, status=WeekStatus.LOCKED)

    repo = ScheduleWeekRepository(db_session)
    purged = await WeekService(repo).purge_old_weeks()

    assert purged == 2
    remaining = await db_session.scalar(select(func.count()).select_from(ScheduleWeek))
    assert remaining == 2


async def test_purge_cascades_to_submissions_and_statuses(db_session, monkeypatch):
    """Deleting an old week removes its submissions and daily statuses (cascade)."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "RETENTION_WEEKS", 1)
    monkeypatch.setattr(settings, "RETENTION_ENABLED", True)

    weeks = await _make_weeks(db_session, 2)
    oldest = min(weeks, key=lambda w: w.start_date)

    user = User(
        phone_number="0501112233", first_name="G", last_name="", roles=[]
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    sub = WeeklySubmission(user_id=user.id, week_id=oldest.id)
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    ds = DailyStatus(submission_id=sub.id, date=oldest.start_date, is_available=True)
    db_session.add(ds)
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    purged = await WeekService(repo).purge_old_weeks()

    assert purged == 1
    sub_count = await db_session.scalar(
        select(func.count()).select_from(WeeklySubmission)
    )
    ds_count = await db_session.scalar(select(func.count()).select_from(DailyStatus))
    assert sub_count == 0  # cascaded away with the week
    assert ds_count == 0


async def test_purge_disabled_is_noop(db_session, monkeypatch):
    """With RETENTION_ENABLED=False nothing is deleted regardless of count."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "RETENTION_ENABLED", False)
    monkeypatch.setattr(settings, "RETENTION_WEEKS", 2)

    await _make_weeks(db_session, 5)

    repo = ScheduleWeekRepository(db_session)
    purged = await WeekService(repo).purge_old_weeks()

    assert purged == 0
    remaining = await db_session.scalar(select(func.count()).select_from(ScheduleWeek))
    assert remaining == 5
