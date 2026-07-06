"""E2E tests — run inside Docker Compose against the full stack.

These tests exercise the real HTTP API (httpx against uvicorn) with a
real PostgreSQL database.  They are designed to run via:
    docker compose -f docker-compose.yml -f docker-compose.test.yml \
        up --build --abort-on-container-exit --exit-code-from e2e

These tests are marked as ``integration`` and skipped in normal pytest runs.
Use ``pytest -m integration`` or ``pytest --run-integration`` to include them.
"""

from __future__ import annotations

import os
import pytest
import httpx

# Skip entire module unless integration tests are explicitly requested
pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("E2E_BASE_URL", "http://backend:8000")
API = f"{BASE_URL}/api/v1"
ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@test.com")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "admin123")
TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def admin_token() -> str:
    """Log in as the seeded admin and return a JWT token."""
    r = httpx.post(
        f"{API}/auth/admin/login",
        json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token: str) -> dict:
    """Authorization headers for admin requests."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def http() -> httpx.Client:
    """Shared httpx client for the session."""
    return httpx.Client(timeout=TIMEOUT)


# ---------------------------------------------------------------------------
# 1. Health & Config
# ---------------------------------------------------------------------------

class TestHealth:
    """Smoke tests: health endpoint returns expected shape."""

    def test_health_check(self, http: httpx.Client):
        r = http.get(f"{BASE_URL}/health")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"


# ---------------------------------------------------------------------------
# 2. Auth
# ---------------------------------------------------------------------------

class TestAuth:
    """Authentication flow: login with valid and invalid credentials."""

    def test_login_success(self, http: httpx.Client):
        r = http.post(
            f"{API}/auth/admin/login",
            json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body

    def test_login_wrong_password(self, http: httpx.Client):
        r = http.post(
            f"{API}/auth/admin/login",
            json={"username": ADMIN_EMAIL, "password": "wrong"},
        )
        assert r.status_code in (401, 403)

    def test_me_authenticated(self, http: httpx.Client, auth_headers: dict):
        r = http.get(f"{API}/auth/me", headers=auth_headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 3. Weeks CRUD
# ---------------------------------------------------------------------------

class TestWeeks:
    """Schedule-week lifecycle: create → list → status update → delete."""

    def test_week_lifecycle(self, http: httpx.Client, auth_headers: dict):
        # --- Create ---
        payload = {
            "start_date": "2026-01-05",
            "end_date": "2026-01-11",
        }
        r = http.post(f"{API}/admin/weeks", json=payload, headers=auth_headers)
        assert r.status_code in (200, 201), f"Create week: {r.text}"
        week = r.json()
        week_id = week["id"]

        # --- List ---
        r = http.get(f"{API}/admin/weeks", headers=auth_headers)
        assert r.status_code == 200
        weeks = r.json()
        assert any(w["id"] == week_id for w in weeks)

        # --- Update status ---
        r = http.patch(
            f"{API}/admin/weeks/{week_id}/status",
            json={"status": "open"},
            headers=auth_headers,
        )
        assert r.status_code == 200, f"Status update: {r.text}"

        # --- Delete ---
        r = http.delete(f"{API}/admin/weeks/{week_id}", headers=auth_headers)
        assert r.status_code in (200, 204), f"Delete week: {r.text}"


# ---------------------------------------------------------------------------
# 4. Users (Guuards)
# ---------------------------------------------------------------------------

class TestUsers:
    """User (guard) CRUD."""

    def test_user_lifecycle(self, http: httpx.Client, auth_headers: dict):
        # --- Create ---
        payload = {
            "full_name": "E2E Test Guard",
            "phone": "0500000000",
        }
        r = http.post(f"{API}/admin/users", json=payload, headers=auth_headers)
        assert r.status_code in (200, 201), f"Create user: {r.text}"
        user = r.json()
        user_id = user["id"]

        # --- List ---
        r = http.get(f"{API}/admin/users", headers=auth_headers)
        assert r.status_code == 200
        users = r.json()
        assert any(u["id"] == user_id for u in users)

        # --- Delete ---
        r = http.delete(f"{API}/admin/users/{user_id}", headers=auth_headers)
        assert r.status_code in (200, 204), f"Delete user: {r.text}"


# ---------------------------------------------------------------------------
# 6. Settings
# ---------------------------------------------------------------------------

class TestSettings:
    """System settings: update and read."""

    def test_settings_get(self, http: httpx.Client, auth_headers: dict):
        # --- Get settings ---
        r = http.get(f"{API}/admin/settings", headers=auth_headers)
        assert r.status_code == 200, f"Get settings: {r.text}"


# ---------------------------------------------------------------------------
# 7. Admins
# ---------------------------------------------------------------------------

class TestAdmins:
    """Admin CRUD: create a sub-admin, list, delete."""

    def test_admin_lifecycle(self, http: httpx.Client, auth_headers: dict):
        # --- Create ---
        payload = {
            "email": "subadmin@test.com",
            "password": "SubAdmin123!",
            "full_name": "Sub Admin",
        }
        r = http.post(f"{API}/admin/admins", json=payload, headers=auth_headers)
        assert r.status_code in (200, 201), f"Create admin: {r.text}"
        admin = r.json()
        admin_id = admin["id"]

        # --- List ---
        r = http.get(f"{API}/admin/admins", headers=auth_headers)
        assert r.status_code == 200
        admins = r.json()
        assert any(a["id"] == admin_id for a in admins)

        # --- Delete ---
        r = http.delete(f"{API}/admin/admins/{admin_id}", headers=auth_headers)
        assert r.status_code in (200, 204), f"Delete admin: {r.text}"


# ---------------------------------------------------------------------------
# 8. Export
# ---------------------------------------------------------------------------

class TestExport:
    """Excel export: requires at least one week."""

    def test_export_returns_file(self, http: httpx.Client, auth_headers: dict):
        # Create a week to export
        week_r = http.post(
            f"{API}/admin/weeks",
            json={"start_date": "2026-03-02", "end_date": "2026-03-08"},
            headers=auth_headers,
        )
        assert week_r.status_code in (200, 201)
        week_id = week_r.json()["id"]

        # Export
        r = http.get(f"{API}/admin/export/week/{week_id}", headers=auth_headers)
        assert r.status_code == 200, f"Export: {r.text}"
        assert r.headers.get("content-type", "").startswith(
            "application"
        ) or "spreadsheet" in r.headers.get("content-type", "")

        # Cleanup
        http.delete(f"{API}/admin/weeks/{week_id}", headers=auth_headers)