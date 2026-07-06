"""Tests for week-status transition validation (P03).

Validates change_week_status for the 3-state model:
  closed ⇄ open, and either closed/open → locked (LOCKED is terminal)
and rejects all illegal transitions (incl. any locked → *) with AppBaseException(400).
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.constants import WeekStatus
from app.exceptions import AppBaseException
from app.services.week_service import WeekService


# ── helpers ────────────────────────────────────────────────────────────


def _mock_week(status: WeekStatus, opened_at=None) -> MagicMock:
    """Create a week-like MagicMock.

    Defaults to a *future*, never-opened week (start_date well ahead of today,
    ``opened_at=None``) so the no-reopen / single-open guard treats it as the
    legitimate upcoming week — the OPEN-target tests rely on this.
    """
    w = MagicMock()
    w.id = uuid.uuid4()
    w.start_date = date(2099, 1, 1)
    w.end_date = date(2099, 1, 7)
    w.status = status
    w.opened_at = opened_at
    return w


def _svc(week) -> WeekService:
    """Return a WeekService with a mock repo returning *week* on get_by_id."""
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = week
    mock_repo.get_current_open_week.return_value = None  # no other OPEN week

    async def _update(wid, **kwargs):
        """Simulate update() mutating the week's fields."""
        for k, v in kwargs.items():
            setattr(week, k, v)
        return week

    mock_repo.update = AsyncMock(side_effect=_update)
    return WeekService(mock_repo)


# ── tests ──────────────────────────────────────────────────────────────


class TestValidTransitions:
    """Happy-path transitions that should succeed."""

    @pytest.mark.asyncio
    async def test_open_to_locked(self):
        week = _mock_week(WeekStatus.OPEN)
        svc = _svc(week)

        result = await svc.change_week_status(week.id, WeekStatus.LOCKED)
        assert result.status == WeekStatus.LOCKED

    @pytest.mark.asyncio
    async def test_open_to_closed(self):
        """The auto-lock TIME closes the submission window: open → closed (reopenable)."""
        week = _mock_week(WeekStatus.OPEN)
        svc = _svc(week)

        result = await svc.change_week_status(week.id, WeekStatus.CLOSED)
        assert result.status == WeekStatus.CLOSED

    @pytest.mark.asyncio
    async def test_closed_to_open(self):
        """Admin opens the upcoming, never-opened week (the only legal open path)."""
        week = _mock_week(WeekStatus.CLOSED)
        svc = _svc(week)

        result = await svc.change_week_status(week.id, WeekStatus.OPEN)
        assert result.status == WeekStatus.OPEN

    @pytest.mark.asyncio
    async def test_closed_to_locked(self):
        """The Sunday rollover finalizes a closed week to LOCKED (the only path to
        LOCKED — publish no longer locks)."""
        week = _mock_week(WeekStatus.CLOSED)
        svc = _svc(week)

        result = await svc.change_week_status(week.id, WeekStatus.LOCKED)
        assert result.status == WeekStatus.LOCKED


class TestOpenedAtStamp:
    """``opened_at`` is stamped on the first OPEN; a week that already ran its
    window (opened_at set) can no longer be reopened (no-reopen decision)."""

    @pytest.mark.asyncio
    async def test_opened_at_stamped_on_first_open(self):
        week = _mock_week(WeekStatus.CLOSED, opened_at=None)
        svc = _svc(week)

        await svc.change_week_status(week.id, WeekStatus.OPEN)
        assert week.opened_at is not None

    @pytest.mark.asyncio
    async def test_reopen_already_opened_week_rejected(self):
        """A CLOSED week whose window already ran (opened_at set) is not reopenable."""
        from datetime import datetime

        week = _mock_week(WeekStatus.CLOSED, opened_at=datetime(2026, 1, 1, 12, 0, 0))
        svc = _svc(week)

        with pytest.raises(ValueError):
            await svc.change_week_status(week.id, WeekStatus.OPEN)


class TestInvalidTransitions:
    """Illegal transitions that must raise AppBaseException."""

    @pytest.mark.asyncio
    async def test_locked_to_closed_rejected(self):
        """LOCKED is the finalized state — it cannot drop back to CLOSED."""
        week = _mock_week(WeekStatus.LOCKED)
        svc = _svc(week)

        with pytest.raises(AppBaseException) as exc_info:
            await svc.change_week_status(week.id, WeekStatus.CLOSED)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_locked_to_open_rejected(self):
        """LOCKED is terminal — it cannot be reopened."""
        week = _mock_week(WeekStatus.LOCKED)
        svc = _svc(week)

        with pytest.raises(AppBaseException) as exc_info:
            await svc.change_week_status(week.id, WeekStatus.OPEN)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_same_status_open_rejected(self):
        """No-op transition open → open is rejected."""
        week = _mock_week(WeekStatus.OPEN)
        svc = _svc(week)

        with pytest.raises(AppBaseException) as exc_info:
            await svc.change_week_status(week.id, WeekStatus.OPEN)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_same_status_locked_rejected(self):
        """No-op transition locked → locked is rejected."""
        week = _mock_week(WeekStatus.LOCKED)
        svc = _svc(week)

        with pytest.raises(AppBaseException) as exc_info:
            await svc.change_week_status(week.id, WeekStatus.LOCKED)
        assert exc_info.value.status_code == 400


# ── create_week default status ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_week_defaults_to_closed():
    """A newly created week starts CLOSED — admin opens it manually."""
    from app.schemas.week_schemas import WeekCreate

    saved = _mock_week(WeekStatus.CLOSED)
    mock_repo = AsyncMock()

    async def _save(week):
        # Echo back the status the service set on the model.
        saved.status = week.status
        saved.start_date = week.start_date
        saved.end_date = week.end_date
        return saved

    mock_repo.save = AsyncMock(side_effect=_save)
    svc = WeekService(mock_repo)

    result = await svc.create_week(
        WeekCreate(start_date=date(2025, 6, 1), end_date=date(2025, 6, 7))
    )
    assert result.status == WeekStatus.CLOSED
