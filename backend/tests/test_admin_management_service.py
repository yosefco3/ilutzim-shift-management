"""
Tests for multi-admin step 02 — AdminManagementService guard rails
[EDGE E2, E3, E4, E6, E8].
"""

import pytest

from app.constants import AdminRole
from app.exceptions import (
    AdminManagementException,
    AdminNotFoundException,
    ConflictException,
    ValidationException,
)
from app.repositories.admin_repository import AdminRepository
from app.services.admin_management_service import AdminManagementService
from app.services.auth_service import AuthService, pwd_context


async def _add_admin(
    repo: AdminRepository,
    email: str,
    role: AdminRole = AdminRole.ADMIN,
):
    return await repo.create_admin(
        email=email,
        password_hash=AuthService.hash_password("strongpass1"),
        full_name="Test Admin",
        role=role,
    )


@pytest.fixture
def service_factory(db_session):
    repo = AdminRepository(db_session)
    return repo, AdminManagementService(repo)


# ── list ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_admins_never_exposes_hash(service_factory):
    repo, service = service_factory
    await _add_admin(repo, "a@a.com", role=AdminRole.SUPER_ADMIN)
    await _add_admin(repo, "b@b.com")

    admins = await service.list_admins()
    assert [a["email"] for a in admins] == ["a@a.com", "b@b.com"]
    for a in admins:
        assert "password_hash" not in a
        assert set(a) == {"id", "email", "full_name", "role", "is_active", "created_at"}


# ── create ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_admin_always_role_admin(service_factory):
    repo, service = service_factory
    created = await service.create_admin("New@Example.COM", "  דוד  ", "abcd123456")

    assert created["role"] == AdminRole.ADMIN.value
    assert created["email"] == "new@example.com"  # normalized
    assert created["full_name"] == "דוד"
    row = await repo.get_by_email("new@example.com")
    assert row is not None and pwd_context.verify("abcd123456", row.password_hash)


@pytest.mark.asyncio
async def test_create_admin_weak_password_rejected(service_factory):
    _, service = service_factory
    with pytest.raises(ValidationException):
        await service.create_admin("a@a.com", "דוד", "short")


@pytest.mark.asyncio
async def test_create_admin_duplicate_email_conflict(service_factory):
    """[E4] duplicate email → clear 409-style error, not a 500."""
    repo, service = service_factory
    await _add_admin(repo, "dup@a.com")
    with pytest.raises(ConflictException):
        await service.create_admin("dup@a.com", "דוד", "abcd123456")


@pytest.mark.asyncio
async def test_create_admin_integrity_race_maps_to_conflict(service_factory, monkeypatch):
    """[E8] two creates race past the pre-check — IntegrityError becomes 409."""
    from sqlalchemy.exc import IntegrityError

    repo, service = service_factory

    async def _boom(**kwargs):
        raise IntegrityError("insert", {}, Exception("unique"))

    monkeypatch.setattr(repo, "create_admin", _boom)
    with pytest.raises(ConflictException):
        await service.create_admin("race@a.com", "דוד", "abcd123456")


@pytest.mark.asyncio
async def test_create_admin_with_viewer_role(service_factory):
    _, service = service_factory
    created = await service.create_admin("v@a.com", "צופה", "abcd123456", role="viewer")
    assert created["role"] == AdminRole.VIEWER.value


@pytest.mark.asyncio
async def test_create_admin_super_admin_role_rejected(service_factory):
    """SUPER_ADMIN is never assignable — the hierarchy keeps one super admin."""
    _, service = service_factory
    with pytest.raises(ValidationException):
        await service.create_admin("x@a.com", "x", "abcd123456", role="super_admin")
    with pytest.raises(ValidationException):
        await service.create_admin("x@a.com", "x", "abcd123456", role="nonsense")


# ── change_role ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_change_role_admin_to_viewer_and_back(service_factory):
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    admin = await _add_admin(repo, "second@a.com")

    updated = await service.change_role(boss.id, admin.id, "viewer")
    assert updated["role"] == AdminRole.VIEWER.value
    updated = await service.change_role(boss.id, admin.id, "admin")
    assert updated["role"] == AdminRole.ADMIN.value


@pytest.mark.asyncio
async def test_change_role_guard_rails(service_factory):
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    other_super = await _add_admin(repo, "other@a.com", role=AdminRole.SUPER_ADMIN)
    admin = await _add_admin(repo, "second@a.com")

    with pytest.raises(AdminManagementException):
        await service.change_role(boss.id, boss.id, "admin")  # self
    with pytest.raises(AdminManagementException):
        await service.change_role(boss.id, other_super.id, "admin")  # demote super
    with pytest.raises(ValidationException):
        await service.change_role(boss.id, admin.id, "super_admin")  # promote to super
    with pytest.raises(AdminNotFoundException):
        await service.change_role(boss.id, 999, "viewer")


# ── set_active ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_deactivate_self(service_factory):
    """[E2]"""
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    with pytest.raises(AdminManagementException):
        await service.set_active(caller_id=boss.id, target_id=boss.id, active=False)


@pytest.mark.asyncio
async def test_cannot_deactivate_super_admin(service_factory):
    """[E3] SUPER_ADMIN accounts cannot be deactivated via the API at all."""
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    other = await _add_admin(repo, "other@a.com", role=AdminRole.SUPER_ADMIN)
    with pytest.raises(AdminManagementException):
        await service.set_active(caller_id=boss.id, target_id=other.id, active=False)


@pytest.mark.asyncio
async def test_deactivate_and_reactivate_regular_admin(service_factory):
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    admin = await _add_admin(repo, "second@a.com")

    off = await service.set_active(boss.id, admin.id, active=False)
    assert off["is_active"] is False
    on = await service.set_active(boss.id, admin.id, active=True)
    assert on["is_active"] is True


@pytest.mark.asyncio
async def test_set_active_unknown_id(service_factory):
    _, service = service_factory
    with pytest.raises(AdminNotFoundException):
        await service.set_active(caller_id=1, target_id=999, active=False)


# ── reset_password ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_password_self_blocked(service_factory):
    """[E6] resetting your own password would bypass the current-password check."""
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    with pytest.raises(AdminManagementException):
        await service.reset_password(boss.id, boss.id, "abcd123456")


@pytest.mark.asyncio
async def test_reset_password_enforces_policy(service_factory):
    """[E6]"""
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    admin = await _add_admin(repo, "second@a.com")
    with pytest.raises(ValidationException):
        await service.reset_password(boss.id, admin.id, "short")


@pytest.mark.asyncio
async def test_reset_password_happy_path(service_factory):
    repo, service = service_factory
    boss = await _add_admin(repo, "boss@a.com", role=AdminRole.SUPER_ADMIN)
    admin = await _add_admin(repo, "second@a.com")

    await service.reset_password(boss.id, admin.id, "newpass1234")
    row = await repo.get_by_id(admin.id)
    assert pwd_context.verify("newpass1234", row.password_hash)


@pytest.mark.asyncio
async def test_reset_password_unknown_id(service_factory):
    _, service = service_factory
    with pytest.raises(AdminNotFoundException):
        await service.reset_password(caller_id=1, target_id=999, new_password="abcd123456")
