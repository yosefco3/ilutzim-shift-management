"""Tests for WeekService.auto_rotate_weeks.

The rotation has a single job: make sure the upcoming Sun–Sat week always
exists, created CLOSED. It must NOT change existing weeks' statuses (no silent
auto-publish) and must NOT duplicate a week that already exists for the range.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.constants import WeekStatus
from app.services.week_service import WeekService
from app.utils.date_utils import week_range


def _week(status, start, end):
    w = MagicMock()
    w.id = uuid.uuid4()
    w.status = status
    w.start_date = start
    w.end_date = end
    return w


@pytest.mark.asyncio
async def test_creates_upcoming_week_as_closed_when_missing():
    """No week for the upcoming range → one is created CLOSED."""
    ws, we = week_range(date.today())
    repo = AsyncMock()
    repo.get_by_date_range.return_value = None
    created = _week(WeekStatus.CLOSED, ws, we)
    repo.save.return_value = created

    svc = WeekService(repo)
    await svc.auto_rotate_weeks()

    repo.save.assert_awaited_once()
    saved_arg = repo.save.call_args.args[0]
    assert saved_arg.status == WeekStatus.CLOSED
    assert saved_arg.start_date == ws
    assert saved_arg.end_date == we


@pytest.mark.asyncio
async def test_does_not_duplicate_existing_upcoming_week():
    """A week already exists for the upcoming range → nothing is created."""
    ws, we = week_range(date.today())
    repo = AsyncMock()
    repo.get_by_date_range.return_value = _week(WeekStatus.CLOSED, ws, we)

    svc = WeekService(repo)
    await svc.auto_rotate_weeks()

    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_auto_publish_expired_weeks():
    """Expired closed/locked weeks keep their status — no silent publish."""
    ws, we = week_range(date.today())
    repo = AsyncMock()
    # Upcoming week already exists, so no creation happens either.
    repo.get_by_date_range.return_value = _week(WeekStatus.CLOSED, ws, we)

    svc = WeekService(repo)
    await svc.auto_rotate_weeks()

    # The rotation must never flip a week's status.
    repo.update.assert_not_awaited()
