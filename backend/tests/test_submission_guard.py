"""Tests for submission status guard — P05."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.submission_controller import router as submission_router
from app.dependencies import (
    get_week_service,
    get_submission_service,
    get_current_user,
    require_admin_role,
)
from datetime import datetime, timezone, date

from app.messages import Messages


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(submission_router)
    return app


def _valid_day(day_index=0):
    return {
        "day_index": day_index,
        "shifts": [{"shift_type": "morning", "from_hour": "07:00", "to_hour": "15:00"}],
    }


def _mock_user(user_id=None):
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


class TestSubmissionStatusGuard:
    """POST /submissions is blocked when week is not open."""

    def test_submit_when_open_week_success(self):
        """Open week → submission accepted (201)."""
        week_id = uuid.uuid4()
        week_start = date(2025, 6, 1)

        week_svc = AsyncMock()
        week_svc.get_current_open_week.return_value = type(
            "Week", (), {"id": week_id, "start_date": week_start}
        )()

        sub_svc = AsyncMock()
        sub_svc.create_submission.return_value = {
            "id": str(uuid.uuid4()),
            "week_id": str(week_id),
            "user_id": str(uuid.uuid4()),
            "status": "submitted",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "days": [],
        }

        user = _mock_user()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(app)

        resp = client.post(
            "/submissions",
            json={"week_id": str(week_id), "days": [_valid_day()]},
            headers={"X-Telegram-Init-Data": "__DEV_MODE__"},
        )
        assert resp.status_code == 201, f"Got {resp.status_code}: {resp.text}"
        app.dependency_overrides.clear()

    def test_submit_when_no_open_week_403(self):
        """No open week → 403 with SUBMISSION_CLOSED message."""
        sub_svc = AsyncMock()
        week_svc = AsyncMock()
        week_svc.get_current_open_week.return_value = None

        user = _mock_user()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(app)

        resp = client.post(
            "/submissions",
            json={"week_id": str(uuid.uuid4()), "days": [_valid_day()]},
            headers={"X-Telegram-Init-Data": "__DEV_MODE__"},
        )
        assert resp.status_code == 403
        assert Messages.SUBMISSION_CLOSED in resp.json()["detail"]
        app.dependency_overrides.clear()

    def test_submit_wrong_week_id_403(self):
        """Open week exists but week_id doesn't match → 403."""
        real_week_id = uuid.uuid4()
        wrong_week_id = uuid.uuid4()
        week_start = date(2025, 6, 1)

        week_svc = AsyncMock()
        week_svc.get_current_open_week.return_value = type(
            "Week", (), {"id": real_week_id, "start_date": week_start}
        )()

        sub_svc = AsyncMock()
        user = _mock_user()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(app)

        resp = client.post(
            "/submissions",
            json={"week_id": str(wrong_week_id), "days": [_valid_day()]},
            headers={"X-Telegram-Init-Data": "__DEV_MODE__"},
        )
        assert resp.status_code == 403
        assert Messages.SUBMISSION_WRONG_WEEK in resp.json()["detail"]
        app.dependency_overrides.clear()

    def test_get_my_submission_ok(self):
        """GET /submissions/my returns submission for authenticated user."""
        user = _mock_user()
        sub_svc = AsyncMock()
        sub_svc.get_submission.return_value = None

        week_svc = AsyncMock()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(app)

        resp = client.get(
            f"/submissions/my?week_id={uuid.uuid4()}",
            headers={"X-Telegram-Init-Data": "__DEV_MODE__"},
        )
        assert resp.status_code == 200
        app.dependency_overrides.clear()

    def test_get_submissions_for_user_admin_allowed(self):
        """GET /submissions/user/{id} works for an authenticated admin."""
        sub_svc = AsyncMock()
        sub_svc.get_submissions_for_user.return_value = []

        week_svc = AsyncMock()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[require_admin_role] = lambda: {"role": "admin"}
        client = TestClient(app)

        resp = client.get(f"/submissions/user/{uuid.uuid4()}")
        assert resp.status_code == 200
        app.dependency_overrides.clear()

    def test_get_submissions_for_user_requires_admin(self):
        """GET /submissions/user/{id} is rejected without admin auth (no token → 403)."""
        app = _make_app()
        client = TestClient(app)

        resp = client.get(f"/submissions/user/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)

    def test_get_submissions_for_week_requires_admin(self):
        """GET /submissions/week/{id} is rejected without admin auth (no token → 403)."""
        app = _make_app()
        client = TestClient(app)

        resp = client.get(f"/submissions/week/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)