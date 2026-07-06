"""Tests for GET /submissions/current-week endpoint (P04).

The route returns the *relevant* week for the guard: the open week when one
exists, otherwise the latest week (closed/locked/published) WITH its status so
the UI can show a status banner. It returns ``null`` only when no week exists.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.submission_controller import router as submission_router
from app.dependencies import get_week_service


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(submission_router)
    return app


def _week_dict(status, week_id=None):
    return {
        "id": week_id or str(uuid.uuid4()),
        "start_date": date(2025, 1, 6),
        "end_date": date(2025, 1, 12),
        "status": status,
        "days": [{"day_index": i, "blocked": False} for i in range(7)],
    }


class TestGetCurrentWeek:
    """Tests for GET /submissions/current-week."""

    def test_get_current_week_open(self):
        """Returns the open week data."""
        week_id = str(uuid.uuid4())
        mock_svc = AsyncMock()
        mock_svc.get_relevant_week_with_days.return_value = _week_dict("open", week_id)

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: mock_svc
        client = TestClient(app)

        resp = client.get("/submissions/current-week")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == week_id
        assert data["status"] == "open"
        assert data["start_date"] == "2025-01-06"
        assert data["end_date"] == "2025-01-12"
        app.dependency_overrides.clear()

    def test_get_current_week_returns_locked_with_status(self):
        """When locked, returns the week WITH status 'locked' (not null)."""
        mock_svc = AsyncMock()
        mock_svc.get_relevant_week_with_days.return_value = _week_dict("locked")

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: mock_svc
        client = TestClient(app)

        resp = client.get("/submissions/current-week")
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"
        app.dependency_overrides.clear()

    def test_get_current_week_returns_locked_with_status(self):
        """When locked, returns the week WITH status 'locked' (not null)."""
        mock_svc = AsyncMock()
        mock_svc.get_relevant_week_with_days.return_value = _week_dict("locked")

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: mock_svc
        client = TestClient(app)

        resp = client.get("/submissions/current-week")
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"
        app.dependency_overrides.clear()

    def test_get_current_week_none_when_no_weeks(self):
        """Returns null only when no weeks exist at all."""
        mock_svc = AsyncMock()
        mock_svc.get_relevant_week_with_days.return_value = None

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: mock_svc
        client = TestClient(app)

        resp = client.get("/submissions/current-week")
        assert resp.status_code == 200
        assert resp.json() is None
        app.dependency_overrides.clear()


class TestGetRelevantWeekWithDaysService:
    """Service-level logic for get_relevant_week_with_days (3-tier fallback)."""

    def _week(self, status):
        from datetime import date as _date
        w = AsyncMock()
        w.id = uuid.uuid4()
        w.status = status
        w.start_date = _date(2025, 1, 6)
        w.end_date = _date(2025, 1, 12)
        return w

    async def _run(self, open_week, current_or_upcoming, latest_week):
        from app.services.week_service import WeekService
        repo = AsyncMock()
        repo.get_current_open_week.return_value = open_week
        repo.get_current_or_upcoming_week.return_value = current_or_upcoming
        repo.get_latest_week.return_value = latest_week
        svc = WeekService(repo)
        return await svc.get_relevant_week_with_days()

    def test_prefers_open_week(self):
        import asyncio
        from app.constants import WeekStatus
        open_w = self._week(WeekStatus.OPEN)
        result = asyncio.run(self._run(open_w, self._week(WeekStatus.CLOSED),
                                       self._week(WeekStatus.LOCKED)))
        assert result.status == WeekStatus.OPEN
        assert len(result.days) == 7

    def test_prefers_current_locked_over_next_closed(self):
        """No open week: the nearest not-yet-ended week (locked current) wins
        over the latest week (next-week closed)."""
        import asyncio
        from app.constants import WeekStatus
        current_locked = self._week(WeekStatus.LOCKED)
        latest_next_closed = self._week(WeekStatus.CLOSED)
        result = asyncio.run(self._run(None, current_locked, latest_next_closed))
        assert result.status == WeekStatus.LOCKED

    def test_falls_back_to_latest_when_all_ended(self):
        """When nothing is open and nothing is still current, show the latest
        (typically a published) week."""
        import asyncio
        from app.constants import WeekStatus
        latest_published = self._week(WeekStatus.LOCKED)
        result = asyncio.run(self._run(None, None, latest_published))
        assert result.status == WeekStatus.LOCKED

    def test_none_when_no_weeks(self):
        import asyncio
        result = asyncio.run(self._run(None, None, None))
        assert result is None
