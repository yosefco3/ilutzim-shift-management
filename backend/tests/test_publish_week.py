"""
Tests for WeekService.publish_week.

Publish is a **pure broadcast**: it sends each guard their personal schedule +
the schedule-grid PNG and stamps ``published_at``, but it NEVER changes the
week's status (the week stays CLOSED) and NEVER creates the next week. Only the
Sunday rollover locks a week (→ LOCKED) and only ``auto_rotate_weeks`` creates
the upcoming week. Covered at the service layer with mocked repos + a mocked
schedule read model.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.constants import WeekStatus
from app.exceptions import InvalidTransitionException
from app.services.week_service import WeekService


def _week(status: WeekStatus, *, published_at=None) -> MagicMock:
    w = MagicMock()
    w.id = uuid.uuid4()
    w.start_date = date(2025, 6, 1)
    w.end_date = date(2025, 6, 7)
    w.status = status
    w.opened_at = None
    w.published_at = published_at
    return w


def _svc(week, *, current=None, summary=None, send_raises=False):
    """WeekService wired with mock repos + schedule read model.

    ``current`` is the week returned by get_upcoming_unstarted_week (defaults to
    ``week`` itself → the week under test is the publishable/upcoming week).
    """
    week_repo = AsyncMock()
    week_repo.get_by_id.return_value = week

    async def _update(wid, **kwargs):
        for k, v in kwargs.items():
            setattr(week, k, v)
        return week

    week_repo.update = AsyncMock(side_effect=_update)
    week_repo.get_upcoming_unstarted_week.return_value = (
        week if current is None else current
    )
    week_repo.get_latest_week.return_value = week if current is None else current

    user_repo = AsyncMock()
    user_repo.get_all.return_value = [MagicMock(telegram_id="1")]

    schedule_export = AsyncMock()
    if send_raises:
        schedule_export.send_personal_schedules.side_effect = RuntimeError("boom")
    else:
        schedule_export.send_personal_schedules.return_value = (
            summary or {"sent": 2, "skipped": 1, "total": 3}
        )

    svc = WeekService(week_repo, user_repo, schedule_export)
    return svc, week_repo, schedule_export


@pytest.fixture(autouse=True)
def _patch_bot(monkeypatch):
    """Patch the notify_* helpers imported inside change_week_status."""
    locked = AsyncMock()
    opened = AsyncMock()
    monkeypatch.setattr("app.bot.notifications.notify_week_locked", locked)
    monkeypatch.setattr("app.bot.notifications.notify_week_opened", opened)
    return locked, opened


class TestFirstPublish:
    async def test_closed_publish_keeps_closed_and_stamps(self, _patch_bot):
        locked, _ = _patch_bot
        week = _week(WeekStatus.CLOSED)
        svc, week_repo, schedule_export = _svc(week)

        result = await svc.publish_week(week.id)

        assert week.status == WeekStatus.CLOSED       # publish never locks
        assert week.published_at is not None          # stamped
        schedule_export.send_personal_schedules.assert_awaited_once()
        assert schedule_export.send_personal_schedules.await_args.args[0] == week.id
        locked.assert_not_awaited()                   # no lock broadcast
        week_repo.save.assert_not_awaited()           # publish does NOT create next week
        assert result == {"sent": 2, "skipped": 1, "total": 3, "republished": False}


class TestRepublish:
    async def test_already_published_closed_rebroadcasts(self):
        # A CLOSED week that already carries published_at → re-publish: broadcast
        # again, still CLOSED, republished=True.
        week = _week(WeekStatus.CLOSED, published_at=date(2025, 5, 30))
        svc, week_repo, schedule_export = _svc(week)

        result = await svc.publish_week(week.id)

        assert result["republished"] is True
        assert result["sent"] == 2
        assert week.status == WeekStatus.CLOSED
        schedule_export.send_personal_schedules.assert_awaited_once()
        assert schedule_export.send_personal_schedules.await_args.args[0] == week.id


class TestRejected:
    async def test_open_week_cannot_publish(self):
        week = _week(WeekStatus.OPEN)
        svc, _, schedule_export = _svc(week)
        with pytest.raises(InvalidTransitionException):
            await svc.publish_week(week.id)
        schedule_export.send_personal_schedules.assert_not_awaited()

    async def test_locked_week_cannot_publish(self):
        # LOCKED is the final, rollover-only state — nothing left to publish.
        week = _week(WeekStatus.LOCKED)
        svc, _, schedule_export = _svc(week)
        with pytest.raises(InvalidTransitionException):
            await svc.publish_week(week.id)
        schedule_export.send_personal_schedules.assert_not_awaited()

    async def test_started_closed_week_rejected(self):
        # A CLOSED week that is no longer the upcoming/unstarted one (it started)
        # is not publishable.
        week = _week(WeekStatus.CLOSED)
        other = _week(WeekStatus.CLOSED)  # a newer week is now the upcoming one
        svc, _, schedule_export = _svc(week, current=other)
        with pytest.raises(InvalidTransitionException):
            await svc.publish_week(week.id)
        schedule_export.send_personal_schedules.assert_not_awaited()


class TestPreviewPublish:
    async def test_delegates_to_read_model_without_sending(self):
        week = _week(WeekStatus.CLOSED)
        svc, _, schedule_export = _svc(week)
        preview = [{"user_name": "אבי", "would_send": True, "message": "..."}]
        schedule_export.preview_personal_schedules.return_value = preview

        result = await svc.preview_publish(week.id)

        assert result is preview
        schedule_export.preview_personal_schedules.assert_awaited_once_with(week.id)
        # Preview never sends and never changes status.
        schedule_export.send_personal_schedules.assert_not_awaited()

    async def test_empty_when_no_read_model(self):
        svc = WeekService(AsyncMock(), AsyncMock(), None)
        assert await svc.preview_publish(uuid.uuid4()) == []


class TestRolloverAndFailures:
    async def test_silent_lock_does_not_send_personal_schedules(self):
        # The Sunday rollover locks via change_week_status(notify=False); it must
        # never trigger the personal-schedule broadcast (that lives in publish).
        week = _week(WeekStatus.OPEN)
        svc, _, schedule_export = _svc(week)
        await svc.change_week_status(week.id, WeekStatus.LOCKED, notify=False)
        schedule_export.send_personal_schedules.assert_not_awaited()

    async def test_broadcast_failure_keeps_closed_and_surfaces(self):
        week = _week(WeekStatus.CLOSED)
        svc, _, schedule_export = _svc(week, send_raises=True)

        result = await svc.publish_week(week.id)

        # published_at is stamped; the failure is surfaced (not swallowed) and the
        # week stays CLOSED so the admin can press publish again.
        assert week.status == WeekStatus.CLOSED
        assert week.published_at is not None
        assert result == {
            "sent": 0, "skipped": 0, "failed": 0, "total": 0, "republished": False
        }
