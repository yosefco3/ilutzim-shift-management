"""
Tests for multi-admin step 03 — /auth/admin/admins* endpoints.

SUPER_ADMIN-only gating, domain-error → HTTP mapping, and the throttle
regression [EDGE E7] (lockout on one account must not affect another).
"""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.constants import AdminRole
from app.dependencies import _get_admin_repo, get_admin_management_service
from app.exceptions import AuthenticationFailedException
from app.main import create_app
from app.repositories.admin_repository import AdminRepository
from app.services.admin_management_service import AdminManagementService
from app.services.auth_service import AuthService
from app.services.login_throttle import get_login_throttle

from datetime import datetime, timedelta, timezone


def _token(sub: str, role: AdminRole) -> str:
    payload = {
        "sub": sub,
        "role": role.value,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _add_admin(repo, email, role=AdminRole.ADMIN):
    return await repo.create_admin(
        email=email,
        password_hash=AuthService.hash_password("strongpass1"),
        full_name="Test Admin",
        role=role,
    )


@pytest_asyncio.fixture
async def api(db_session):
    """App with the management service wired to the in-memory test DB, plus a
    seeded SUPER_ADMIN ('boss') and a regular ADMIN ('second')."""
    repo = AdminRepository(db_session)
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    second = await _add_admin(repo, "second@a.com")

    app = create_app()
    app.dependency_overrides[get_admin_management_service] = (
        lambda: AdminManagementService(AdminRepository(db_session))
    )
    # get_current_admin verifies is_active against the DB (step 04) — point it
    # at the same in-memory session the seeded admins live in.
    app.dependency_overrides[_get_admin_repo] = lambda: AdminRepository(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, boss, second


# ── role gating ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_endpoints_reject_non_super(api):
    ac, boss, second = api
    headers = _auth(_token(str(second.id), AdminRole.ADMIN))

    assert (await ac.get("/auth/admin/admins", headers=headers)).status_code == 403
    assert (
        await ac.post(
            "/auth/admin/admins",
            headers=headers,
            json={"email": "x@a.com", "full_name": "x", "password": "abcd123456"},
        )
    ).status_code == 403
    assert (
        await ac.patch(
            f"/auth/admin/admins/{boss.id}/active",
            headers=headers,
            json={"active": False},
        )
    ).status_code == 403
    assert (
        await ac.post(
            f"/auth/admin/admins/{boss.id}/reset-password",
            headers=headers,
            json={"new_password": "abcd123456"},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_endpoints_require_token(api):
    ac, _, _ = api
    resp = await ac.get("/auth/admin/admins")
    assert resp.status_code in (401, 403)


# ── list / create ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_admins_no_hashes(api):
    ac, boss, _ = api
    resp = await ac.get(
        "/auth/admin/admins", headers=_auth(_token(str(boss.id), AdminRole.SUPER_ADMIN))
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert "password_hash" not in str(data)


@pytest.mark.asyncio
async def test_create_then_duplicate_409(api):
    ac, boss, _ = api
    headers = _auth(_token(str(boss.id), AdminRole.SUPER_ADMIN))
    body = {"email": "third@a.com", "full_name": "שלישי", "password": "abcd123456"}

    resp = await ac.post("/auth/admin/admins", headers=headers, json=body)
    assert resp.status_code == 201
    assert resp.json()["role"] == AdminRole.ADMIN.value

    resp = await ac.post("/auth/admin/admins", headers=headers, json=body)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_weak_password_422(api):
    ac, boss, _ = api
    headers = _auth(_token(str(boss.id), AdminRole.SUPER_ADMIN))
    resp = await ac.post(
        "/auth/admin/admins",
        headers=headers,
        json={"email": "x@a.com", "full_name": "x", "password": "short"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_email_422(api):
    ac, boss, _ = api
    headers = _auth(_token(str(boss.id), AdminRole.SUPER_ADMIN))
    resp = await ac.post(
        "/auth/admin/admins",
        headers=headers,
        json={"email": "not-an-email", "full_name": "x", "password": "abcd123456"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_with_role_and_change_role(api):
    ac, boss, second = api
    headers = _auth(_token(str(boss.id), AdminRole.SUPER_ADMIN))

    resp = await ac.post(
        "/auth/admin/admins",
        headers=headers,
        json={
            "email": "viewer@a.com",
            "full_name": "צופה",
            "password": "abcd123456",
            "role": "viewer",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "viewer"

    resp = await ac.patch(
        f"/auth/admin/admins/{second.id}/role", headers=headers, json={"role": "viewer"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"

    # invalid role → 422, super_admin target → 400, self → 400
    resp = await ac.patch(
        f"/auth/admin/admins/{second.id}/role",
        headers=headers,
        json={"role": "super_admin"},
    )
    assert resp.status_code == 422
    resp = await ac.patch(
        f"/auth/admin/admins/{boss.id}/role", headers=headers, json={"role": "admin"}
    )
    assert resp.status_code == 400


# ── set_active / reset-password mapping ───────────────────────────────────────

@pytest.mark.asyncio
async def test_self_deactivate_400_unknown_404_other_200(api):
    ac, boss, second = api
    headers = _auth(_token(str(boss.id), AdminRole.SUPER_ADMIN))

    resp = await ac.patch(
        f"/auth/admin/admins/{boss.id}/active", headers=headers, json={"active": False}
    )
    assert resp.status_code == 400

    resp = await ac.patch(
        "/auth/admin/admins/99999/active", headers=headers, json={"active": False}
    )
    assert resp.status_code == 404

    resp = await ac.patch(
        f"/auth/admin/admins/{second.id}/active", headers=headers, json={"active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_reset_password_mapping(api):
    ac, boss, second = api
    headers = _auth(_token(str(boss.id), AdminRole.SUPER_ADMIN))

    resp = await ac.post(
        f"/auth/admin/admins/{boss.id}/reset-password",
        headers=headers,
        json={"new_password": "abcd123456"},
    )
    assert resp.status_code == 400  # self-reset blocked

    resp = await ac.post(
        f"/auth/admin/admins/{second.id}/reset-password",
        headers=headers,
        json={"new_password": "abcd123456"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── [E7] throttle isolation between accounts ──────────────────────────────────

class _TwoAccountAuthService:
    """Only 'b@a.com' with 'right-pass1' succeeds."""

    async def login_admin(self, username, password):
        if username == "b@a.com" and password == "right-pass1":
            return {"access_token": "tok", "token_type": "bearer"}
        raise AuthenticationFailedException()


@pytest.mark.asyncio
async def test_lockout_on_one_account_does_not_affect_other():
    from app.dependencies import get_auth_service

    get_login_throttle().clear()
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: _TwoAccountAuthService()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            for _ in range(5):
                resp = await ac.post(
                    "/auth/admin/login",
                    json={"username": "a@a.com", "password": "wrong"},
                )
                assert resp.status_code == 401
            # account A is now locked
            resp = await ac.post(
                "/auth/admin/login", json={"username": "a@a.com", "password": "wrong"}
            )
            assert resp.status_code == 429
            # account B logs in fine
            resp = await ac.post(
                "/auth/admin/login",
                json={"username": "b@a.com", "password": "right-pass1"},
            )
            assert resp.status_code == 200
    finally:
        get_login_throttle().clear()
