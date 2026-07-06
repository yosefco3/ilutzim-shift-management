"""Tests for submission success notification and the detailed submissions endpoint.

Uses the dependency-override mock style (see test_week_workflow.py) — no real DB.
"""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.constants import WeekStatus
from app.controllers.admin_weeks_controller import router as admin_weeks_router
from app.controllers.submission_controller import router as submission_router
from app.dependencies import (
    get_current_user,
    get_submission_service,
    get_week_service,
    require_admin_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin_weeks_router)
    app.include_router(submission_router)
    return app


def _admin_payload():
    return {"sub": "admin1", "role": "super_admin"}


def _mock_user(telegram_id=123456, user_id=None):
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.telegram_id = telegram_id
    return user


def _week_obj(week_id=None, start_date="2026-06-08", end_date="2026-06-14"):
    wid = week_id or uuid.uuid4()
    return type(
        "Week",
        (),
        {
            "id": wid,
            "status": WeekStatus.OPEN,
            "start_date": date.fromisoformat(start_date),
            "end_date": date.fromisoformat(end_date),
        },
    )()


def _submission_obj(sub_id=None, week_id=None, user_id=None, general_notes="test notes"):
    return {
        "id": str(sub_id or uuid.uuid4()),
        "week_id": str(week_id or uuid.uuid4()),
        "user_id": str(user_id or uuid.uuid4()),
        "general_notes": general_notes,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "days": [],
    }


def _valid_payload(week_id):
    return {
        "week_id": str(week_id),
        "general_notes": "test notes",
        "days": [
            {
                "day_index": 0,
                "shifts": [
                    {"shift_type": "morning", "from_hour": "07:00", "to_hour": "16:00"},
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Notification on successful submission
# ---------------------------------------------------------------------------

class TestSubmissionSuccessNotification:
    """POST /submissions triggers a Telegram notification when telegram_id is set."""

    def test_submit_sends_notification(self):
        week_id = uuid.uuid4()
        user = _mock_user(telegram_id=987654)

        week_svc = AsyncMock()
        week_svc.get_current_open_week.return_value = _week_obj(week_id)
        sub_svc = AsyncMock()
        sub_svc.create_submission.return_value = _submission_obj(week_id=week_id, user_id=user.id)

        app = _make_app()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc

        with patch(
            "app.bot.notifications.notify_submission_success", new_callable=AsyncMock
        ) as mock_notify:
            mock_notify.return_value = True
            client = TestClient(app)
            resp = client.post("/submissions", json=_valid_payload(week_id))

        assert resp.status_code == 201
        mock_notify.assert_called_once()
        args = mock_notify.call_args[0]
        assert isinstance(args[0], int)          # telegram_id
        assert isinstance(args[1], str)          # week label
        assert "/" in args[1]                    # DD/MM/YYYY - DD/MM/YYYY

    def test_submit_skips_notification_without_telegram_id(self):
        week_id = uuid.uuid4()
        user = _mock_user(telegram_id=None)

        week_svc = AsyncMock()
        week_svc.get_current_open_week.return_value = _week_obj(week_id)
        sub_svc = AsyncMock()
        sub_svc.create_submission.return_value = _submission_obj(week_id=week_id, user_id=user.id)

        app = _make_app()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc

        with patch(
            "app.bot.notifications.notify_submission_success", new_callable=AsyncMock
        ) as mock_notify:
            client = TestClient(app)
            resp = client.post("/submissions", json=_valid_payload(week_id))

        assert resp.status_code == 201
        mock_notify.assert_not_called()


class TestNotificationsNonCritical:
    """Notification failure must not affect the submission API response."""

    def test_submit_succeeds_when_notification_errors(self):
        week_id = uuid.uuid4()
        user = _mock_user(telegram_id=555)

        week_svc = AsyncMock()
        week_svc.get_current_open_week.return_value = _week_obj(week_id)
        sub_svc = AsyncMock()
        sub_svc.create_submission.return_value = _submission_obj(
            week_id=week_id, user_id=user.id, general_notes=""
        )

        app = _make_app()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_week_service] = lambda: week_svc
        app.dependency_overrides[get_submission_service] = lambda: sub_svc

        with patch(
            "app.bot.notifications.notify_submission_success",
            new_callable=AsyncMock,
            side_effect=Exception("Boom"),
        ):
            client = TestClient(app)
            resp = client.post("/submissions", json=_valid_payload(week_id))

        # Still 201 despite the notification blowing up
        assert resp.status_code == 201
        assert resp.json()["general_notes"] == ""


# ---------------------------------------------------------------------------
# Detailed submissions endpoint
# ---------------------------------------------------------------------------

class TestDetailedSubmissions:
    """GET /admin/weeks/{id}/submissions/detailed returns submitted + missing."""

    def test_returns_submitted_and_missing_with_shift_data(self):
        week_id = uuid.uuid4()
        submitted_user_id = uuid.uuid4()

        detailed = {
            "submitted": [
                {
                    "id": str(uuid.uuid4()),
                    "user_id": str(submitted_user_id),
                    "week_id": str(week_id),
                    "full_name": "דנה לוי",
                    "general_notes": "submitted notes",
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "days": [
                        {
                            "id": str(uuid.uuid4()),
                            "date": "2026-06-08",
                            "is_available": True,
                            "shift_windows": [
                                {
                                    "id": str(uuid.uuid4()),
                                    "shift_type": "morning",
                                    "start_time": "07:00:00",
                                    "end_time": "16:00:00",
                                }
                            ],
                        }
                    ],
                }
            ],
            "missing": [
                {
                    "user_id": str(uuid.uuid4()),
                    "full_name": "יוסי כהן",
                    "phone_number": "0500000000",
                }
            ],
            "week_label": "08/06/2026 - 14/06/2026",
        }

        sub_svc = AsyncMock()
        sub_svc.get_week_submissions_detailed.return_value = detailed

        app = _make_app()
        app.dependency_overrides[require_admin_role] = lambda: _admin_payload()
        app.dependency_overrides[get_submission_service] = lambda: sub_svc

        client = TestClient(app)
        resp = client.get(f"/admin/weeks/{week_id}/submissions/detailed")

        assert resp.status_code == 200
        data = resp.json()
        assert "submitted" in data and "missing" in data and "week_label" in data
        assert len(data["submitted"]) == 1
        assert len(data["missing"]) == 1

        s = data["submitted"][0]
        assert s["user_id"] == str(submitted_user_id)
        assert s["full_name"] == "דנה לוי"
        assert s["general_notes"] == "submitted notes"
        # Shift data present
        assert len(s["days"]) == 1
        assert s["days"][0]["shift_windows"][0]["shift_type"] == "morning"
