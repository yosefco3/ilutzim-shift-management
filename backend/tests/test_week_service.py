"""Week lifecycle: single-open-week + no-reopen invariants (B-1 · B-4 · B-7).

Product decision (2026-07-03): a week is never reopened, and at most one week is
OPEN at any time. These tests pin the structural DB guards (this file) and the
service-layer guards (added alongside the no-reopen / publish-surface steps).
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.constants import WeekStatus
from app.messages import Messages
from app.models.schedule_week import ScheduleWeek
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.services.week_service import WeekService

_REF = date(2026, 7, 1)  # a fixed "today" for the no-reopen guard tests
_UPCOMING = date(2026, 7, 5)  # Sunday, > _REF
_PAST = date(2026, 6, 21)  # Sunday, < _REF


# ── published_at API surface ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_week_response_exposes_published_at(db_session):
    """WeekResponse round-trips published_at from the model (NULL by default)."""
    from app.schemas.week_schemas import WeekResponse

    week = ScheduleWeek(
        start_date=_UPCOMING, end_date=_UPCOMING + timedelta(days=6),
        status=WeekStatus.CLOSED,
    )
    db_session.add(week)
    await db_session.commit()
    await db_session.refresh(week)

    resp = WeekResponse.model_validate(week)
    assert resp.published_at is None

    stamp = datetime(2026, 7, 3, 9, 0, 0)
    week.published_at = stamp
    await db_session.commit()
    await db_session.refresh(week)
    assert WeekResponse.model_validate(week).published_at == stamp


# ── DB structural guards (B-4 + single-open partial index) ───────────────────

@pytest.mark.asyncio
async def test_duplicate_week_range_rejected(db_session):
    """Two weeks with the same (start_date, end_date) violate the unique
    constraint — blocks the concurrent auto_rotate_weeks duplicate-week race."""
    start = date(2026, 7, 5)
    end = start + timedelta(days=6)
    db_session.add(ScheduleWeek(start_date=start, end_date=end, status=WeekStatus.CLOSED))
    await db_session.flush()
    db_session.add(ScheduleWeek(start_date=start, end_date=end, status=WeekStatus.LOCKED))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_two_open_weeks_rejected_at_db(db_session):
    """The partial unique index (uq_one_open_week) forbids a second OPEN row,
    even for two different date ranges."""
    w1_start = date(2026, 7, 5)
    w2_start = date(2026, 7, 12)
    db_session.add(ScheduleWeek(
        start_date=w1_start, end_date=w1_start + timedelta(days=6), status=WeekStatus.OPEN
    ))
    await db_session.flush()
    db_session.add(ScheduleWeek(
        start_date=w2_start, end_date=w2_start + timedelta(days=6), status=WeekStatus.OPEN
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()


# ── Service-layer no-reopen + single-open guard (B-1 · B-7) ──────────────────

async def _svc_and_week(db_session, *, start, status, opened_at=None):
    week = ScheduleWeek(
        start_date=start, end_date=start + timedelta(days=6),
        status=status, opened_at=opened_at,
    )
    db_session.add(week)
    await db_session.commit()
    return WeekService(ScheduleWeekRepository(db_session)), week


@pytest.mark.asyncio
async def test_reopen_old_closed_week_rejected(db_session):
    """A CLOSED week whose submission window already ran (opened_at set) can't
    be reopened."""
    svc, week = await _svc_and_week(
        db_session, start=_UPCOMING, status=WeekStatus.CLOSED,
        opened_at=datetime(2026, 6, 1, 12, 0),
    )
    with patch("app.services.week_service.today_il", return_value=_REF):
        with pytest.raises(ValueError, match=Messages.VAL_WEEK_ALREADY_RAN):
            await svc.change_week_status(week.id, WeekStatus.OPEN)


@pytest.mark.asyncio
async def test_open_past_week_rejected(db_session):
    """A week that has already started (start_date <= today) can't be opened."""
    svc, week = await _svc_and_week(
        db_session, start=_PAST, status=WeekStatus.CLOSED, opened_at=None,
    )
    with patch("app.services.week_service.today_il", return_value=_REF):
        with pytest.raises(ValueError, match=Messages.VAL_WEEK_NOT_UPCOMING):
            await svc.change_week_status(week.id, WeekStatus.OPEN)


@pytest.mark.asyncio
async def test_open_second_week_while_one_open_rejected(db_session):
    """With one week already OPEN, opening another upcoming week is rejected."""
    already_open = ScheduleWeek(
        start_date=_PAST, end_date=_PAST + timedelta(days=6), status=WeekStatus.OPEN,
    )
    upcoming = ScheduleWeek(
        start_date=_UPCOMING, end_date=_UPCOMING + timedelta(days=6),
        status=WeekStatus.CLOSED, opened_at=None,
    )
    db_session.add_all([already_open, upcoming])
    await db_session.commit()
    svc = WeekService(ScheduleWeekRepository(db_session))
    with patch("app.services.week_service.today_il", return_value=_REF):
        with pytest.raises(ValueError, match=Messages.VAL_ANOTHER_WEEK_OPEN):
            await svc.change_week_status(upcoming.id, WeekStatus.OPEN)


@pytest.mark.asyncio
async def test_open_upcoming_fresh_week_ok(db_session):
    """The legitimate path — upcoming, never-opened, no other OPEN — still works."""
    svc, week = await _svc_and_week(
        db_session, start=_UPCOMING, status=WeekStatus.CLOSED, opened_at=None,
    )
    with patch("app.services.week_service.today_il", return_value=_REF):
        result = await svc.change_week_status(week.id, WeekStatus.OPEN)
    assert result.status == WeekStatus.OPEN
    await db_session.refresh(week)
    assert week.opened_at is not None


# ── Repo resilience + publish failure surfacing (B-low) ──────────────────────

@pytest.mark.asyncio
async def test_get_current_open_week_survives_two_open_rows(db_session):
    """Even if corrupt data slips two OPEN rows past the partial index, the hot
    path returns one (the most recent) rather than raising MultipleResultsFound."""
    # Drop the single-open guard to simulate the corrupt state it normally prevents.
    await db_session.execute(text("DROP INDEX uq_one_open_week"))
    db_session.add_all([
        ScheduleWeek(start_date=_PAST, end_date=_PAST + timedelta(days=6),
                     status=WeekStatus.OPEN),
        ScheduleWeek(start_date=_UPCOMING, end_date=_UPCOMING + timedelta(days=6),
                     status=WeekStatus.OPEN),
    ])
    await db_session.commit()

    repo = ScheduleWeekRepository(db_session)
    result = await repo.get_current_open_week()  # must not raise
    assert result is not None
    assert result.start_date == _UPCOMING  # most recent by start_date


@pytest.mark.asyncio
async def test_publish_reports_broadcast_failures(db_session):
    """A partial broadcast failure surfaces as failed > 0, and the week stays
    CLOSED with published_at stamped (publish never locks)."""
    week = ScheduleWeek(
        start_date=_UPCOMING, end_date=_UPCOMING + timedelta(days=6),
        status=WeekStatus.CLOSED, opened_at=None,
    )
    db_session.add(week)
    await db_session.commit()

    schedule_export = AsyncMock()
    schedule_export.send_personal_schedules = AsyncMock(
        return_value={"sent": 1, "skipped": 0, "failed": 2, "total": 3}
    )
    svc = WeekService(
        ScheduleWeekRepository(db_session), None, schedule_export_service=schedule_export
    )
    result = await svc.publish_week(week.id)

    assert result["failed"] == 2
    await db_session.refresh(week)
    assert week.status == WeekStatus.CLOSED  # publish never locks
    assert week.published_at is not None  # stamped even on partial failure
