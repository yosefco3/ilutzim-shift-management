"""
Tests for brute-force lockout on admin login (prompt 04):
  - LoginThrottle unit behaviour with an injected clock
  - controller returns 429 after too many failures, 401 otherwise, and a
    successful login resets the counter
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_auth_service
from app.exceptions import AuthenticationFailedException
from app.main import create_app
from app.services.login_throttle import LoginThrottle, get_login_throttle


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


# ── unit tests ──────────────────────────────────────────────────────────────────

def test_locks_after_max_attempts():
    clock = _Clock()
    th = LoginThrottle(max_attempts=3, window_seconds=900, lockout_seconds=600, time_fn=clock)
    assert not th.is_locked("a@b.com")
    th.record_failure("a@b.com")
    th.record_failure("a@b.com")
    assert not th.is_locked("a@b.com")
    th.record_failure("a@b.com")  # 3rd → locked
    assert th.is_locked("a@b.com")
    assert th.minutes_until_unlock("a@b.com") == 10


def test_key_is_normalized():
    th = LoginThrottle(max_attempts=2, time_fn=_Clock())
    th.record_failure("Yosef@X.com ")
    th.record_failure(" yosef@x.com")
    assert th.is_locked("YOSEF@x.com")


def test_reset_clears_counter():
    clock = _Clock()
    th = LoginThrottle(max_attempts=2, time_fn=clock)
    th.record_failure("a")
    th.reset("a")
    th.record_failure("a")
    assert not th.is_locked("a")


def test_lock_expires_after_lockout():
    clock = _Clock()
    th = LoginThrottle(max_attempts=2, window_seconds=900, lockout_seconds=600, time_fn=clock)
    th.record_failure("a")
    th.record_failure("a")
    assert th.is_locked("a")
    clock.advance(600)
    assert not th.is_locked("a")
    # fresh attempts allowed — a single failure must not immediately re-lock
    th.record_failure("a")
    assert not th.is_locked("a")


def test_window_expiry_resets_count():
    clock = _Clock()
    th = LoginThrottle(max_attempts=3, window_seconds=100, lockout_seconds=600, time_fn=clock)
    th.record_failure("a")
    th.record_failure("a")
    clock.advance(101)  # window elapsed → counter restarts
    th.record_failure("a")
    assert not th.is_locked("a")


# ── controller integration ──────────────────────────────────────────────────────

class _StubAuthService:
    """Accepts only username 'good' with password 'right'."""

    async def login_admin(self, username, password):
        if username == "good" and password == "right":
            return {"access_token": "tok", "token_type": "bearer"}
        raise AuthenticationFailedException()


@pytest.fixture
def throttled_app():
    get_login_throttle().clear()
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: _StubAuthService()
    yield app
    get_login_throttle().clear()


async def _login(app, username, password):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.post(
            "/auth/admin/login", json={"username": username, "password": password}
        )


@pytest.mark.asyncio
async def test_login_locks_after_five_failures(throttled_app):
    for _ in range(5):
        resp = await _login(throttled_app, "victim", "wrong")
        assert resp.status_code == 401
    # 6th attempt is blocked even though we stop guessing
    resp = await _login(throttled_app, "victim", "wrong")
    assert resp.status_code == 429
    assert "דקות" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_successful_login_resets_counter(throttled_app):
    for _ in range(4):
        assert (await _login(throttled_app, "good", "wrong")).status_code == 401
    # success before hitting the limit
    assert (await _login(throttled_app, "good", "right")).status_code == 200
    # counter reset → four more failures still allowed (not locked yet)
    for _ in range(4):
        assert (await _login(throttled_app, "good", "wrong")).status_code == 401


@pytest.mark.asyncio
async def test_normal_login_unaffected(throttled_app):
    resp = await _login(throttled_app, "good", "right")
    assert resp.status_code == 200
