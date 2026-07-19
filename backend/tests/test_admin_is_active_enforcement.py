"""
Tests for multi-admin step 04 [EDGE E5] — get_current_admin enforces is_active
against the DB on every request, so deactivation locks out immediately
(not after token expiry).
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.constants import AdminRole
from app.dependencies import _get_admin_repo
from app.main import create_app
from app.repositories.admin_repository import AdminRepository
from app.services.auth_service import AuthService


def _token(sub: str, role: AdminRole = AdminRole.SUPER_ADMIN) -> str:
    payload = {
        "sub": sub,
        "role": role.value,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")


@pytest_asyncio.fixture
async def api(db_session):
    repo = AdminRepository(db_session)
    admin = await repo.create_admin(
        email="boss@a.com",
        password_hash=AuthService.hash_password("strongpass1"),
        full_name="Boss",
        role=AdminRole.SUPER_ADMIN,
    )
    app = create_app()
    app.dependency_overrides[_get_admin_repo] = lambda: AdminRepository(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, repo, admin


@pytest.mark.asyncio
async def test_active_admin_passes(api):
    ac, _, admin = api
    resp = await ac.get(
        "/auth/me", headers={"Authorization": f"Bearer {_token(str(admin.id))}"}
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_deactivated_admin_rejected_with_valid_token(api):
    ac, repo, admin = api
    token = _token(str(admin.id))
    await repo.update_admin(admin.id, is_active=False)

    resp = await ac.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_deleted_admin_rejected_not_500(api):
    ac, _, _ = api
    resp = await ac.get(
        "/auth/me", headers={"Authorization": f"Bearer {_token('99999')}"}
    )
    assert resp.status_code == 401
