"""
Tests for multi-admin step 01 [EDGE E1]:
  - login lookup matches exact email or exact local part (never a prefix guess,
    never MultipleResultsFound with several admins)
  - require_super_admin dependency gates by role
"""

import pytest

from app.config import Settings
from app.constants import AdminRole
from app.exceptions import AuthenticationFailedException
from app.repositories.admin_repository import AdminRepository
from app.services.auth_service import AuthService


def _make_settings() -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///test.db",
        TELEGRAM_BOT_TOKEN="test-token",
        APP_URL="http://localhost:3000",
        ADMIN_API_KEY="key",
        JWT_SECRET_KEY="x" * 40,
        ENVIRONMENT="dev",
        DEV_AUTH_BYPASS_ENABLED=False,
    )


async def _add_admin(repo: AdminRepository, email: str, password: str = "strongpass1"):
    return await repo.create_admin(
        email=email,
        password_hash=AuthService.hash_password(password),
        full_name="Test Admin",
        role=AdminRole.ADMIN,
    )


# ── lookup semantics ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lookup_exact_local_part(db_session):
    repo = AdminRepository(db_session)
    await _add_admin(repo, "yosef@a.com")
    await _add_admin(repo, "yosefco@b.com")

    found = await repo.get_by_username_or_email("yosef")
    assert found is not None and found.email == "yosef@a.com"


@pytest.mark.asyncio
async def test_lookup_prefix_no_longer_matches(db_session):
    """'yos' is a prefix of the local part, not the full local part → no match."""
    repo = AdminRepository(db_session)
    await _add_admin(repo, "yosef@a.com")

    assert await repo.get_by_username_or_email("yos") is None


@pytest.mark.asyncio
async def test_lookup_shared_local_part_is_ambiguous(db_session):
    """Two admins with the same local part: bare local part matches neither
    (no guessing, no MultipleResultsFound); full email still works."""
    repo = AdminRepository(db_session)
    await _add_admin(repo, "x@a.com")
    await _add_admin(repo, "x@b.com")

    assert await repo.get_by_username_or_email("x") is None
    found = await repo.get_by_username_or_email("x@b.com")
    assert found is not None and found.email == "x@b.com"


@pytest.mark.asyncio
async def test_lookup_wildcards_not_interpreted(db_session):
    """SQL wildcards in the input must not widen the match."""
    repo = AdminRepository(db_session)
    await _add_admin(repo, "yosef@a.com")

    assert await repo.get_by_username_or_email("%") is None
    assert await repo.get_by_username_or_email("y_sef") is None


# ── login through the service ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_full_email_with_multiple_admins(db_session):
    repo = AdminRepository(db_session)
    await _add_admin(repo, "x@a.com", password="passworda1")
    await _add_admin(repo, "x@b.com", password="passwordb2")
    service = AuthService(repo, _make_settings())

    result = await service.login_admin("x@b.com", "passwordb2")
    assert result["role"] == AdminRole.ADMIN.value

    with pytest.raises(AuthenticationFailedException):
        await service.login_admin("x", "passwordb2")  # ambiguous local part


# ── require_super_admin ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_require_super_admin_rejects_admin_role():
    from fastapi import HTTPException

    from app.dependencies import require_super_admin

    with pytest.raises(HTTPException) as exc:
        await require_super_admin(admin={"sub": "2", "role": AdminRole.ADMIN.value})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_super_admin_accepts_super_admin():
    from app.dependencies import require_super_admin

    payload = {"sub": "1", "role": AdminRole.SUPER_ADMIN.value}
    assert await require_super_admin(admin=payload) is payload
