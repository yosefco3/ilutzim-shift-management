"""Tests for the edit gating in SubmissionService.create_submission (3-state model).

- LOCKED is final: submissions can no longer be edited by anyone — not even an
  admin via override_lock.
- CLOSED: an admin may edit on behalf of guards (override_lock=True); a guard
  without override is blocked.
- OPEN: everyone may submit.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.constants import WeekStatus
from app.exceptions import WeekLockedException
from app.services.submission_service import SubmissionService


def _data(days=None):
    d = MagicMock()
    d.user_id = uuid.uuid4()
    d.week_id = uuid.uuid4()
    d.general_notes = None
    d.days = days or []
    return d


def _service(week_status):
    user_repo = AsyncMock()
    user_repo.get_by_id.return_value = MagicMock()  # user exists
    week_repo = AsyncMock()
    week_repo.get_by_id.return_value = type("Week", (), {"status": week_status})()
    sub_repo = AsyncMock()
    sub_repo.upsert_submission.return_value = MagicMock()
    return SubmissionService(sub_repo, user_repo, week_repo), sub_repo


@pytest.mark.asyncio
async def test_admin_cannot_edit_locked_week():
    """override_lock does NOT bypass a LOCKED (final) week → WeekLockedException."""
    svc, sub_repo = _service(WeekStatus.LOCKED)

    with pytest.raises(WeekLockedException):
        await svc.create_submission(_data(), override_lock=True)

    # It must reject before writing anything.
    sub_repo.upsert_submission.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_can_edit_closed_week():
    """A CLOSED week is editable by the admin on behalf of guards (override_lock=True)."""
    svc, sub_repo = _service(WeekStatus.CLOSED)

    with patch(
        "app.services.submission_service.SubmissionResponse.model_validate",
        lambda v: v,
    ):
        await svc.create_submission(_data(), override_lock=True)

    sub_repo.upsert_submission.assert_awaited_once()


@pytest.mark.asyncio
async def test_guard_cannot_edit_closed_week():
    """A guard (no override) is blocked on a CLOSED week."""
    svc, sub_repo = _service(WeekStatus.CLOSED)

    with pytest.raises(WeekLockedException):
        await svc.create_submission(_data(), override_lock=False)

    sub_repo.upsert_submission.assert_not_awaited()


@pytest.mark.asyncio
async def test_guard_cannot_edit_locked_week():
    """A guard (no override) is likewise blocked on a LOCKED week."""
    svc, sub_repo = _service(WeekStatus.LOCKED)

    with pytest.raises(WeekLockedException):
        await svc.create_submission(_data(), override_lock=False)

    sub_repo.upsert_submission.assert_not_awaited()
