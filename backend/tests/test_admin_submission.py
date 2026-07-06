"""Tests for admin-filled submissions — POST /submissions/admin.

An admin fills constraints on behalf of a guard who has no Telegram. Unlike the
guard endpoint, this works regardless of week status (override_lock=True).
"""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from unittest.mock import patch

from app.controllers.submission_controller import router as submission_router
from app.dependencies import (
    get_week_service,
    get_submission_service,
    get_user_service,
    require_admin_role,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(submission_router)
    return app


def _week_obj(week_id, start_date=date(2025, 6, 1), end_date=date(2025, 6, 7)):
    return type(
        "Week", (), {"id": week_id, "start_date": start_date, "end_date": end_date}
    )()


def _user_svc(telegram_id=None):
    """A user_service mock whose get_user returns a guard with the given telegram_id."""
    svc = AsyncMock()
    svc.get_user.return_value = type("Guard", (), {"telegram_id": telegram_id})()
    return svc


def _valid_day(day_index=0):
    return {
        "day_index": day_index,
        "shifts": [{"shift_type": "morning", "from_hour": "07:00", "to_hour": "15:00"}],
    }


def _fake_submission(week_id, user_id):
    return {
        "id": str(uuid.uuid4()),
        "week_id": str(week_id),
        "user_id": str(user_id),
        "general_notes": None,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "days": [],
    }


class TestAdminSubmission:
    """POST /submissions/admin lets an admin submit for a guard."""

    def test_admin_submit_success_overrides_lock(self):
        """Admin submission succeeds and calls create_submission with override_lock=True."""
        week_id = uuid.uuid4()
        user_id = uuid.uuid4()
        week_start = date(2025, 6, 1)

        week_svc = AsyncMock()
        week_svc.get_week.return_value = _week_obj(week_id, start_date=week_start)

        sub_svc = AsyncMock()
        sub_svc.create_submission.return_value = _fake_submission(week_id, user_id)

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_user_service] = lambda: _user_svc(telegram_id=None)
        app.dependency_overrides[require_admin_role] = lambda: None
        client = TestClient(app)

        resp = client.post(
            "/submissions/admin",
            json={
                "user_id": str(user_id),
                "week_id": str(week_id),
                "days": [_valid_day()],
            },
        )
        assert resp.status_code == 201, f"Got {resp.status_code}: {resp.text}"

        # override_lock must be True so closed/locked weeks are allowed
        _, kwargs = sub_svc.create_submission.call_args
        assert kwargs.get("override_lock") is True

        # The submission must target the explicit guard user_id
        created = sub_svc.create_submission.call_args[0][0]
        assert str(created.user_id) == str(user_id)
        app.dependency_overrides.clear()

    def test_admin_get_submission_returns_existing(self):
        """GET /submissions/admin returns the guard's existing submission for edit."""
        week_id = uuid.uuid4()
        user_id = uuid.uuid4()

        sub_svc = AsyncMock()
        sub_svc.get_submission.return_value = _fake_submission(week_id, user_id)
        week_svc = AsyncMock()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[require_admin_role] = lambda: None
        client = TestClient(app)

        resp = client.get(
            "/submissions/admin",
            params={"user_id": str(user_id), "week_id": str(week_id)},
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        sub_svc.get_submission.assert_awaited_once()
        app.dependency_overrides.clear()

    def test_admin_get_submission_null_when_none(self):
        """GET /submissions/admin returns null when the guard hasn't submitted."""
        sub_svc = AsyncMock()
        sub_svc.get_submission.return_value = None
        week_svc = AsyncMock()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[require_admin_role] = lambda: None
        client = TestClient(app)

        resp = client.get(
            "/submissions/admin",
            params={"user_id": str(uuid.uuid4()), "week_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200
        assert resp.json() is None
        app.dependency_overrides.clear()

    def test_admin_submit_requires_user_id(self):
        """Missing user_id → 422 validation error."""
        week_id = uuid.uuid4()
        week_svc = AsyncMock()
        sub_svc = AsyncMock()

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_user_service] = lambda: _user_svc()
        app.dependency_overrides[require_admin_role] = lambda: None
        client = TestClient(app)

        resp = client.post(
            "/submissions/admin",
            json={"week_id": str(week_id), "days": [_valid_day()]},
        )
        assert resp.status_code == 422
        app.dependency_overrides.clear()


class TestAdminSubmissionNotification:
    """When the admin fills for a guard who has Telegram, the guard is notified."""

    def _run(self, telegram_id):
        week_id = uuid.uuid4()
        user_id = uuid.uuid4()

        week_svc = AsyncMock()
        week_svc.get_week.return_value = _week_obj(week_id)
        sub_svc = AsyncMock()
        sub_svc.create_submission.return_value = _fake_submission(week_id, user_id)

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_user_service] = lambda: _user_svc(telegram_id=telegram_id)
        app.dependency_overrides[require_admin_role] = lambda: None

        with patch(
            "app.bot.notifications.notify_admin_filled_constraints",
            new_callable=AsyncMock,
        ) as mock_notify:
            mock_notify.return_value = True
            client = TestClient(app)
            resp = client.post(
                "/submissions/admin",
                json={
                    "user_id": str(user_id),
                    "week_id": str(week_id),
                    "days": [_valid_day()],
                },
            )
        app.dependency_overrides.clear()
        return resp, mock_notify

    def test_notifies_guard_with_telegram(self):
        resp, mock_notify = self._run(telegram_id="987654")
        assert resp.status_code == 201, f"Got {resp.status_code}: {resp.text}"
        mock_notify.assert_called_once()
        args = mock_notify.call_args[0]
        assert args[0] == 987654          # telegram_id as int
        assert isinstance(args[1], str)   # week label
        assert "/" in args[1]             # DD/MM/YYYY - DD/MM/YYYY

    def test_skips_guard_without_telegram(self):
        resp, mock_notify = self._run(telegram_id=None)
        assert resp.status_code == 201, f"Got {resp.status_code}: {resp.text}"
        mock_notify.assert_not_called()

    def test_notification_failure_does_not_break_submission(self):
        week_id = uuid.uuid4()
        user_id = uuid.uuid4()

        week_svc = AsyncMock()
        week_svc.get_week.return_value = _week_obj(week_id)
        sub_svc = AsyncMock()
        sub_svc.create_submission.return_value = _fake_submission(week_id, user_id)

        app = _make_app()
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[get_user_service] = lambda: _user_svc(telegram_id="555")
        app.dependency_overrides[require_admin_role] = lambda: None

        with patch(
            "app.bot.notifications.notify_admin_filled_constraints",
            new_callable=AsyncMock,
            side_effect=Exception("Boom"),
        ):
            client = TestClient(app)
            resp = client.post(
                "/submissions/admin",
                json={
                    "user_id": str(user_id),
                    "week_id": str(week_id),
                    "days": [_valid_day()],
                },
            )
        assert resp.status_code == 201, f"Got {resp.status_code}: {resp.text}"
        app.dependency_overrides.clear()
