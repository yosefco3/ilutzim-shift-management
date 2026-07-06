"""Tests for GET /submissions/constraint-rules.

Public endpoint that exposes the admin-editable constraint thresholds to the
guard form (as ints), so the form can show soft, non-blocking warnings.
"""

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.submission_controller import router as submission_router
from app.dependencies import get_settings_service
from app.services.settings_service import SETTINGS_DEFAULTS


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(submission_router)
    return app


def test_returns_defaults_as_ints():
    """With no DB overrides, returns the SETTINGS_DEFAULTS thresholds as ints."""
    svc = AsyncMock()
    svc.get_setting.side_effect = lambda key: SETTINGS_DEFAULTS[key]

    app = _make_app()
    app.dependency_overrides[get_settings_service] = lambda: svc
    client = TestClient(app)

    resp = client.get("/submissions/constraint-rules")
    assert resp.status_code == 200
    assert resp.json() == {
        "min_shifts_per_guard": 5,
        "min_nights": 2,
        "min_evenings": 2,
        "max_consecutive_days": 6,
    }
    app.dependency_overrides.clear()


def test_parses_string_db_values_to_int():
    """DB values arrive as strings; they are coerced to int."""
    svc = AsyncMock()
    svc.get_setting.side_effect = lambda key: {"min_nights": "4"}.get(key, "1")

    app = _make_app()
    app.dependency_overrides[get_settings_service] = lambda: svc
    client = TestClient(app)

    data = client.get("/submissions/constraint-rules").json()
    assert data["min_nights"] == 4
    assert all(isinstance(v, int) for v in data.values())
    app.dependency_overrides.clear()
