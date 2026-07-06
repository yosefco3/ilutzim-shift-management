"""
Tests for the admin change-password flow (prompt 02):
  - AuthService.change_password logic (wrong current / weak new / same / success)
  - controller takes admin_id from the token, not the body
  - protected endpoint rejects an invalid token
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_auth_service, get_current_admin
from app.exceptions import PasswordChangeException
from app.main import create_app
from app.services.auth_service import AuthService


# ── service-level tests with an in-memory fake repo ─────────────────────────────

class _FakeAdmin:
    def __init__(self, password_hash: str, is_active: bool = True):
        self.id = 1
        self.password_hash = password_hash
        self.is_active = is_active


class _FakeAdminRepo:
    def __init__(self, admin):
        self._admin = admin
        self.updated = {}

    async def get_by_id(self, admin_id):
        return self._admin if (self._admin and admin_id == self._admin.id) else None

    async def update_admin(self, admin_id, **kwargs):
        self.updated = kwargs
        for k, v in kwargs.items():
            setattr(self._admin, k, v)
        return self._admin


def _service(admin):
    return AuthService(_FakeAdminRepo(admin), settings=None)


@pytest.mark.asyncio
async def test_change_password_success():
    admin = _FakeAdmin(AuthService.hash_password("oldpass1234"))
    svc = _service(admin)
    await svc.change_password(1, "oldpass1234", "newpass5678")
    # new password now verifies, old does not
    from app.services.auth_service import pwd_context
    assert pwd_context.verify("newpass5678", admin.password_hash)
    assert not pwd_context.verify("oldpass1234", admin.password_hash)


@pytest.mark.asyncio
async def test_change_password_wrong_current():
    admin = _FakeAdmin(AuthService.hash_password("oldpass1234"))
    with pytest.raises(PasswordChangeException):
        await _service(admin).change_password(1, "WRONG", "newpass5678")


@pytest.mark.asyncio
async def test_change_password_weak_new():
    admin = _FakeAdmin(AuthService.hash_password("oldpass1234"))
    with pytest.raises(PasswordChangeException):
        await _service(admin).change_password(1, "oldpass1234", "short")


@pytest.mark.asyncio
async def test_change_password_same_as_current():
    admin = _FakeAdmin(AuthService.hash_password("oldpass1234"))
    with pytest.raises(PasswordChangeException):
        await _service(admin).change_password(1, "oldpass1234", "oldpass1234")


@pytest.mark.asyncio
async def test_change_password_inactive_admin():
    admin = _FakeAdmin(AuthService.hash_password("oldpass1234"), is_active=False)
    with pytest.raises(PasswordChangeException):
        await _service(admin).change_password(1, "oldpass1234", "newpass5678")


# ── controller-level tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_endpoint_uses_admin_id_from_token_not_body():
    """The endpoint must change the password of the token holder, ignoring any
    id in the body."""
    app = create_app()
    seen = {}

    class _StubService:
        async def change_password(self, admin_id, current_password, new_password):
            seen["admin_id"] = admin_id

    app.dependency_overrides[get_current_admin] = lambda: {"sub": "42", "role": "admin"}
    app.dependency_overrides[get_auth_service] = lambda: _StubService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/auth/admin/change-password",
            json={"current_password": "oldpass1234", "new_password": "newpass5678"},
        )
    assert resp.status_code == 200
    assert seen["admin_id"] == 42


@pytest.mark.asyncio
async def test_endpoint_rejects_invalid_token():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/auth/admin/change-password",
            headers={"Authorization": "Bearer not-a-real-token"},
            json={"current_password": "oldpass1234", "new_password": "newpass5678"},
        )
    assert resp.status_code == 401
