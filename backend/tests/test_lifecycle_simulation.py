"""Time-travel simulation of the full week lifecycle.

These tests fake the clock (patch ``today_il`` as imported into week_service)
and walk whole weeks end-to-end, the way production actually experiences them:
rollover → open → submissions close → build board → publish/re-publish →
rollover locks. They exist because the flow is date-driven and cannot be
exercised manually without waiting real weeks.

Fixed calendar used throughout (2026): 07-01 is a Wednesday, 07-05 / 07-12 /
07-19 are Sundays. Weeks run Sunday–Saturday.
"""

from datetime import date
from unittest.mock import patch

import pytest

from app.constants import WeekStatus
from app.exceptions import InvalidTransitionException
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.services.week_service import WeekService

WED = date(2026, 7, 1)
THU = date(2026, 7, 2)
SUN_1 = date(2026, 7, 5)   # W1 starts
SUN_2 = date(2026, 7, 12)  # W2 starts
SUN_3 = date(2026, 7, 19)  # W3 starts


def at(day: date):
    """Freeze the lifecycle clock at ``day`` (the symbol week_service uses)."""
    return patch("app.services.week_service.today_il", return_value=day)


@pytest.fixture
def service(db_session):
    return WeekService(ScheduleWeekRepository(db_session))


@pytest.fixture
def repo(db_session):
    return ScheduleWeekRepository(db_session)


async def assert_single_open(repo):
    """Invariant: at most one OPEN week at any moment."""
    weeks = await repo.get_all()
    open_weeks = [w for w in weeks if w.status == WeekStatus.OPEN]
    assert len(open_weeks) <= 1, f"invariant broken: {len(open_weeks)} OPEN weeks"


@pytest.mark.asyncio
async def test_full_three_week_happy_path(service, repo):
    """The canonical cycle, three weeks in a row."""
    # --- Wednesday before W1: first boot creates the upcoming week ---
    with at(WED):
        await service.auto_advance_weeks()
        weeks = await repo.get_all()
        assert len(weeks) == 1
        w1 = weeks[0]
        assert (w1.start_date, w1.end_date) == (SUN_1, date(2026, 7, 11))
        assert w1.status == WeekStatus.CLOSED and w1.opened_at is None

        # Idempotent: repeated runs change nothing.
        await service.auto_advance_weeks()
        await service.auto_advance_weeks()
        assert len(await repo.get_all()) == 1

        # Publish before the window even ran — allowed (W1 is the upcoming
        # unstarted week) and keeps it CLOSED.
        # But first: open the submission window.
        opened = await service.change_week_status(w1.id, WeekStatus.OPEN)
        assert opened.status == WeekStatus.OPEN
        w1_db = await repo.get_by_id(w1.id)
        assert w1_db.opened_at is not None
        await assert_single_open(repo)

        # Publish while OPEN is rejected.
        with pytest.raises(InvalidTransitionException):
            await service.publish_week(w1.id)

    # --- Thursday: the auto-lock time closes the window (reversibly) ---
    with at(THU):
        closed = await service.auto_lock_open_week()
        assert closed is not None and closed.status == WeekStatus.CLOSED

        # No auto-reopen: the cron candidate query must skip a week whose
        # window already ran.
        assert await service.auto_open_relevant_week() is None

        # Manual reopen of a week that already ran is refused too.
        with pytest.raises(ValueError):
            await service.change_week_status(w1.id, WeekStatus.OPEN)

        # Publish → stays CLOSED, stamps published_at, first time not a re-publish.
        result = await service.publish_week(w1.id)
        assert result["republished"] is False
        w1_db = await repo.get_by_id(w1.id)
        assert w1_db.status == WeekStatus.CLOSED
        first_published_at = w1_db.published_at
        assert first_published_at is not None

        # Re-publish → still CLOSED, republished=True, timestamp refreshed.
        result = await service.publish_week(w1.id)
        assert result["republished"] is True
        w1_db = await repo.get_by_id(w1.id)
        assert w1_db.status == WeekStatus.CLOSED
        assert w1_db.published_at >= first_published_at

        # Mid-cycle rollover run is a no-op for statuses (W1 hasn't started).
        await service.auto_advance_weeks()
        w1_db = await repo.get_by_id(w1.id)
        assert w1_db.status == WeekStatus.CLOSED
        assert len(await repo.get_all()) == 1

    # --- Sunday 00:00: rollover finalizes W1 and creates W2 ---
    with at(SUN_1):
        await service.auto_advance_weeks()
        weeks = {w.start_date: w for w in await repo.get_all()}
        assert len(weeks) == 2
        assert weeks[SUN_1].status == WeekStatus.LOCKED
        w2 = weeks[SUN_2]
        assert w2.status == WeekStatus.CLOSED and w2.opened_at is None

        # LOCKED is terminal: no publish, no delete, no transitions.
        with pytest.raises(InvalidTransitionException):
            await service.publish_week(weeks[SUN_1].id)
        with pytest.raises(InvalidTransitionException):
            await service.delete_week(weeks[SUN_1].id)
        with pytest.raises(InvalidTransitionException):
            await service.change_week_status(weeks[SUN_1].id, WeekStatus.OPEN)

        # W2 cycle starts: auto-open picks exactly W2.
        opened = await service.auto_open_relevant_week()
        assert opened is not None and opened.id == w2.id
        await assert_single_open(repo)

        # While W2 is OPEN a second week can't be opened (single-open rule).
        # (No second candidate exists yet, but the guard itself must hold if
        #  someone tries to reopen W2 → same-status is rejected as a no-op.)
        with pytest.raises(InvalidTransitionException):
            await service.change_week_status(w2.id, WeekStatus.OPEN)

    # --- Thursday of W1's execution week: close + publish W2 ---
    with at(date(2026, 7, 9)):
        await service.auto_lock_open_week()
        result = await service.publish_week(w2.id)
        assert result["republished"] is False
        assert (await repo.get_by_id(w2.id)).status == WeekStatus.CLOSED

    # --- Next Sunday: W2 locks, W3 appears; W1 untouched ---
    with at(SUN_2):
        await service.auto_advance_weeks()
        weeks = {w.start_date: w for w in await repo.get_all()}
        assert len(weeks) == 3
        assert weeks[SUN_1].status == WeekStatus.LOCKED
        assert weeks[SUN_2].status == WeekStatus.LOCKED
        assert weeks[SUN_3].status == WeekStatus.CLOSED
        assert weeks[SUN_3].opened_at is None
        await assert_single_open(repo)


@pytest.mark.asyncio
async def test_missed_rollover_self_heals_on_next_load(service, repo):
    """Server down at Sunday midnight → first weeks-list load days later
    converges: the started week is finalized and the new upcoming week exists."""
    with at(WED):
        await service.auto_advance_weeks()
        w1 = (await repo.get_all())[0]
        await service.change_week_status(w1.id, WeekStatus.OPEN)

    # Nothing ran on Sunday. First activity is Tuesday.
    with at(date(2026, 7, 7)):
        await service.auto_advance_weeks()
        weeks = {w.start_date: w for w in await repo.get_all()}
        assert weeks[SUN_1].status == WeekStatus.LOCKED  # healed
        assert weeks[SUN_2].status == WeekStatus.CLOSED  # created
        await assert_single_open(repo)


@pytest.mark.asyncio
async def test_publish_gates_track_the_upcoming_week(service, repo):
    """Only the nearest unstarted week is publishable; the button target moves
    at rollover exactly like the backend gate."""
    with at(WED):
        await service.auto_advance_weeks()
        w1 = (await repo.get_all())[0]
        await service.change_week_status(w1.id, WeekStatus.OPEN)
    with at(THU):
        await service.auto_lock_open_week()
        await service.publish_week(w1.id)  # fine: upcoming + CLOSED

    with at(SUN_1):
        await service.auto_advance_weeks()
        weeks = {w.start_date: w for w in await repo.get_all()}
        w2 = weeks[SUN_2]
        # W1 started+locked → rejected; W2 (upcoming, CLOSED) → allowed even
        # though its window never ran (publish is a pure broadcast).
        with pytest.raises(InvalidTransitionException):
            await service.publish_week(weeks[SUN_1].id)
        result = await service.publish_week(w2.id)
        assert result["republished"] is False
        assert (await repo.get_by_id(w2.id)).status == WeekStatus.CLOSED


@pytest.mark.asyncio
async def test_skipped_week_does_not_brick_the_next_cycle(service, repo):
    """A week nobody ever opened must not shadow the next week's auto-open.

    W1 is created but never opened (automation off / admin away). At the Sunday
    rollover W1 is deliberately NOT locked (never ran its window). The next
    cycle's auto-open must still be able to open W2 — the real upcoming target.
    """
    with at(WED):
        await service.auto_advance_weeks()
        w1 = (await repo.get_all())[0]
        assert w1.opened_at is None  # nobody opened it

    with at(SUN_1):
        await service.auto_advance_weeks()
        weeks = {w.start_date: w for w in await repo.get_all()}
        assert weeks[SUN_1].status == WeekStatus.CLOSED  # not locked — by design
        assert weeks[SUN_2].status == WeekStatus.CLOSED

    # Monday: the auto-open cron fires for the new cycle. It must open W2,
    # not choke on the stale, already-started, never-opened W1.
    with at(date(2026, 7, 6)):
        opened = await service.auto_open_relevant_week()
        assert opened is not None, (
            "auto-open returned None: the stale never-opened started week "
            "shadowed the upcoming week in get_upcoming_closed_week"
        )
        assert opened.start_date == SUN_2
        await assert_single_open(repo)
