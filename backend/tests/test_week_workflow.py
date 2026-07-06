"""Integration tests — full week lifecycle (P09).

Tests the complete flow:
  admin opens week → guard submits → admin locks → admin publishes.
Also covers invalid transitions and notification verification.
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
from app.messages import Messages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    """Build a FastAPI app with both admin-weeks and submission routers."""
    app = FastAPI()
    app.include_router(admin_weeks_router)
    app.include_router(submission_router)
    return app


def _admin_payload():
    """Fake decoded-admin payload used to override auth."""
    return {"sub": "admin1", "role": "super_admin"}


def _admin_headers():
    """Bearer header dict — the actual value doesn't matter because
    ``get_current_admin`` is overridden."""
    return {"Authorization": "Bearer faketoken"}


def _valid_day(day_index=0):
    return {
        "day_index": day_index,
        "shifts": [
            {"shift_type": "morning", "from_hour": "07:00", "to_hour": "15:00"}
        ],
    }


def _mock_user(user_id=None):
    """Fake authenticated guard. telegram_id=None skips the notification path."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.telegram_id = None
    return user


def _week_obj(
    week_id=None,
    status=WeekStatus.OPEN,
    start_date="2026-06-08",
    end_date="2026-06-14",
):
    """Build a lightweight week-like object with all attributes."""
    wid = week_id or uuid.uuid4()
    return type(
        "Week",
        (),
        {
            "id": wid,
            "status": status,
            "start_date": date.fromisoformat(start_date),
            "end_date": date.fromisoformat(end_date),
        },
    )()


def _week_with_days_obj(
    week_id=None,
    status=WeekStatus.OPEN,
    start_date="2026-06-08",
    end_date="2026-06-14",
):
    """Build a week-like object with the 7 days the submission form expects."""
    wid = week_id or uuid.uuid4()
    return type(
        "WeekWithDays",
        (),
        {
            "id": wid,
            "status": status,
            "start_date": date.fromisoformat(start_date),
            "end_date": date.fromisoformat(end_date),
            "days": [
                type("Day", (), {"day_index": i, "blocked": False})()
                for i in range(7)
            ],
        },
    )()


def _submission_obj(sub_id=None, week_id=None):
    sid = sub_id or uuid.uuid4()
    wid = week_id or uuid.uuid4()
    return {
        "id": str(sid),
        "week_id": str(wid),
        "user_id": str(uuid.uuid4()),
        "status": "submitted",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "days": [],
    }


def _setup_app(week_svc, sub_svc=None):
    """Create app with dependency overrides pre-configured."""
    app = _make_app()
    app.dependency_overrides[require_admin_role] = lambda: _admin_payload()
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[get_week_service] = lambda: week_svc
    if sub_svc is not None:
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
    return app


# ===========================================================================
# 1. Full week lifecycle
# ===========================================================================
class TestFullWeekLifecycle:
    """End-to-end: open → submit → lock → publish → open next."""

    def test_full_lifecycle(self):
        week_id = uuid.uuid4()
        next_week_id = uuid.uuid4()
        sub_id = uuid.uuid4()

        week_svc = AsyncMock()
        sub_svc = AsyncMock()

        # --- configure current-week call sequence ---
        # Route GET /submissions/current-week calls get_relevant_week_with_days
        week_svc.get_relevant_week_with_days.side_effect = [
            None,                                              # Step 1: no week yet
            _week_with_days_obj(week_id),                      # Step 4: after open → open week
            _week_with_days_obj(week_id, WeekStatus.LOCKED),   # Step 7: after lock → locked week (with status)
        ]

        # Route POST /submissions calls get_current_open_week (guard check)
        week_svc.get_current_open_week.side_effect = [
            None,                          # Step 2: submission blocked (no open week)
            _week_obj(week_id),            # Step 5: submit guard check (week open)
            None,                          # Step 8: submission blocked (locked)
        ]

        sub_svc.create_submission.return_value = _submission_obj(sub_id, week_id)

        # All status transitions go through change_week_status (controller):
        #   open (step 3) → locked by rollover (step 6) → open next week (step 9)
        week_svc.change_week_status.side_effect = [
            _week_obj(week_id, WeekStatus.OPEN),
            _week_obj(week_id, WeekStatus.LOCKED),
            _week_obj(next_week_id, WeekStatus.OPEN,
                      start_date="2026-06-15", end_date="2026-06-21"),
        ]

        app = _setup_app(week_svc, sub_svc)
        client = TestClient(app)

        # Step 1: No weeks → current-week returns null
        resp = client.get("/submissions/current-week")
        assert resp.status_code == 200
        assert resp.json() is None

        # Step 2: Guard cannot submit (no open week)
        resp = client.post(
            "/submissions",
            json={"week_id": str(uuid.uuid4()), "days": [_valid_day()]},
        )
        assert resp.status_code == 403

        # Step 3: Admin opens the (closed) week via {id}/open → change_week_status
        resp = client.post(f"/admin/weeks/{week_id}/open", headers=_admin_headers())
        assert resp.status_code == 200
        week = resp.json()
        assert week["status"] == "open"

        # Step 4: Get current week returns the open week
        resp = client.get("/submissions/current-week")
        assert resp.status_code == 200
        assert resp.json()["status"] == "open"

        # Step 5: Guard can now submit
        resp = client.post(
            "/submissions",
            json={"week_id": str(week_id), "days": [_valid_day()]},
        )
        assert resp.status_code == 201

        # Step 6: The week is locked (LOCKED = the Sunday rollover's final state;
        # here driven via the status endpoint to simulate it at the controller layer)
        resp = client.patch(
            f"/admin/weeks/{week_id}/status",
            json={"status": "locked"},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200

        # Step 7: Get current week now returns the locked week WITH its status
        # (so the guard UI can show a "locked" banner instead of "no week").
        resp = client.get("/submissions/current-week")
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"

        # Step 8: Guard cannot submit anymore
        resp = client.post(
            "/submissions",
            json={"week_id": str(week_id), "days": [_valid_day()]},
        )
        assert resp.status_code == 403

        # Step 9: Admin opens the NEXT (auto-created closed) week — different dates.
        # LOCKED (step 6) is the rollover's terminal state; publish never locks and
        # there is no separate PUBLISHED state in the 3-state model.
        resp = client.post(f"/admin/weeks/{next_week_id}/open", headers=_admin_headers())
        assert resp.status_code == 200
        new_week = resp.json()
        assert new_week["start_date"] != week["start_date"]

        app.dependency_overrides.clear()


# ===========================================================================
# 2. Invalid transitions
# ===========================================================================
class TestInvalidTransitions:
    """Guards against illegal state changes."""

    def test_cannot_reopen_locked(self):
        """Reopening a LOCKED (terminal) week should fail — LOCKED is final."""
        week_id = uuid.uuid4()
        week_svc = AsyncMock()
        # Controller catches all Exception in status endpoint → 400
        week_svc.change_week_status.side_effect = ValueError(
            "Invalid transition"
        )

        app = _setup_app(week_svc)
        client = TestClient(app)

        resp = client.patch(
            f"/admin/weeks/{week_id}/status",
            json={"status": "open"},
            headers=_admin_headers(),
        )
        assert resp.status_code == 400

        app.dependency_overrides.clear()

    def test_cannot_lock_nonexistent_week(self):
        """Locking a week that doesn't exist → service raises → 400."""
        week_svc = AsyncMock()
        # Controller catches Exception and returns 400
        week_svc.change_week_status.side_effect = ValueError("Week not found")

        app = _setup_app(week_svc)
        client = TestClient(app)

        resp = client.patch(
            f"/admin/weeks/{uuid.uuid4()}/status",
            json={"status": "locked"},
            headers=_admin_headers(),
        )
        assert resp.status_code == 400

        app.dependency_overrides.clear()


class TestPublishEndpoint:
    """POST /admin/weeks/{id}/publish returns the broadcast summary."""

    def test_publish_returns_summary(self):
        week_id = uuid.uuid4()
        week_svc = AsyncMock()
        week_svc.publish_week.return_value = {
            "sent": 3, "skipped": 1, "failed": 0, "total": 4, "republished": False,
        }

        app = _setup_app(week_svc)
        client = TestClient(app)

        resp = client.post(
            f"/admin/weeks/{week_id}/publish", headers=_admin_headers()
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "sent": 3, "skipped": 1, "failed": 0, "total": 4, "republished": False,
        }
        week_svc.publish_week.assert_awaited_once()
        app.dependency_overrides.clear()

    def test_publish_non_current_locked_maps_to_400(self):
        from app.exceptions import InvalidTransitionException

        week_svc = AsyncMock()
        week_svc.publish_week.side_effect = InvalidTransitionException(
            "השבוע כבר אינו פעיל"
        )

        app = _setup_app(week_svc)
        client = TestClient(app)

        resp = client.post(
            f"/admin/weeks/{uuid.uuid4()}/publish", headers=_admin_headers()
        )
        assert resp.status_code == 400
        app.dependency_overrides.clear()


# ===========================================================================
# 3. Notification sent on open
# ===========================================================================
class TestNotificationOnOpen:
    """Verify that opening a week goes through change_week_status (which notifies)."""

    def test_open_goes_through_change_status(self):
        week_id = uuid.uuid4()
        week_svc = AsyncMock()
        week_svc.change_week_status.return_value = _week_obj(week_id, WeekStatus.OPEN)

        app = _setup_app(week_svc)
        client = TestClient(app)

        resp = client.post(f"/admin/weeks/{week_id}/open", headers=_admin_headers())

        assert resp.status_code == 200
        # The {id}/open route transitions via change_week_status, which is where
        # notify_week_opened is dispatched for all guards with a telegram_id.
        week_svc.change_week_status.assert_called_once()
        args = week_svc.change_week_status.call_args.args
        assert args[1] == WeekStatus.OPEN

        app.dependency_overrides.clear()


