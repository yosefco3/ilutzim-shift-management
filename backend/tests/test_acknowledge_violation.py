"""Tests for PATCH /submissions/{id}/acknowledge-violation.

An admin acknowledges a submission's rule violations so the submissions grid
hides the orange violation marker.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.submission_controller import router as submission_router
from app.dependencies import get_submission_service, require_admin_role


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(submission_router)
    return app


def _fake_submission(submission_id, acknowledged):
    return {
        "id": str(submission_id),
        "week_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "general_notes": None,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "violation_acknowledged": acknowledged,
        "days": [],
    }


class TestAcknowledgeViolation:
    def test_acknowledge_defaults_to_true(self):
        """An empty body acknowledges the violation (acknowledged defaults True)."""
        submission_id = uuid.uuid4()
        sub_svc = AsyncMock()
        sub_svc.set_violation_acknowledged.return_value = _fake_submission(
            submission_id, True
        )

        app = _make_app()
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[require_admin_role] = lambda: None
        client = TestClient(app)

        resp = client.patch(f"/submissions/{submission_id}/acknowledge-violation", json={})
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        assert resp.json()["violation_acknowledged"] is True
        sub_svc.set_violation_acknowledged.assert_awaited_once_with(submission_id, True)
        app.dependency_overrides.clear()

    def test_can_clear_acknowledgement(self):
        """Passing acknowledged=false un-acknowledges (restores the marker)."""
        submission_id = uuid.uuid4()
        sub_svc = AsyncMock()
        sub_svc.set_violation_acknowledged.return_value = _fake_submission(
            submission_id, False
        )

        app = _make_app()
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[require_admin_role] = lambda: None
        client = TestClient(app)

        resp = client.patch(
            f"/submissions/{submission_id}/acknowledge-violation",
            json={"acknowledged": False},
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        assert resp.json()["violation_acknowledged"] is False
        sub_svc.set_violation_acknowledged.assert_awaited_once_with(submission_id, False)
        app.dependency_overrides.clear()

    def test_missing_submission_returns_404(self):
        """Unknown submission id → 404."""
        submission_id = uuid.uuid4()
        sub_svc = AsyncMock()
        sub_svc.set_violation_acknowledged.return_value = None

        app = _make_app()
        app.dependency_overrides[get_submission_service] = lambda: sub_svc
        app.dependency_overrides[require_admin_role] = lambda: None
        client = TestClient(app)

        resp = client.patch(f"/submissions/{submission_id}/acknowledge-violation", json={})
        assert resp.status_code == 404
        app.dependency_overrides.clear()
