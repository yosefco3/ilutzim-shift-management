"""
Tests for the optional preferred_shift guard field.

Covers the service layer: persistence on create (including the payroll
fields that previously were silently dropped on create), and clearing the
preference via an empty string on update.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.user import User
from app.schemas.user_schemas import UserCreate, UserUpdate
from app.services.user_service import UserService


def _make_repo():
    """Repo mock whose save() fills in DB-generated fields."""
    repo = AsyncMock()

    async def fake_save(user: User) -> User:
        if getattr(user, "id", None) is None:
            user.id = uuid.uuid4()
        if getattr(user, "created_at", None) is None:
            user.created_at = datetime(2026, 7, 4, 12, 0, 0)
        if user.is_active is None:
            user.is_active = True
        return user

    repo.save.side_effect = fake_save
    return repo


def _base_create(**overrides) -> UserCreate:
    data = dict(
        phone_number="0521234567",
        first_name="ישראל",
        last_name="ישראלי",
        roles=["AHMASH"],
    )
    data.update(overrides)
    return UserCreate(**data)


@pytest.mark.asyncio
@patch.object(UserService, "_try_send_welcome_notification", new_callable=AsyncMock)
async def test_create_persists_preferred_shift(mock_notify):
    repo = _make_repo()
    service = UserService(repo)

    resp = await service.create_user(_base_create(preferred_shift="night"))

    saved_user = repo.save.call_args[0][0]
    assert saved_user.preferred_shift == "night"
    assert resp.preferred_shift == "night"


@pytest.mark.asyncio
@patch.object(UserService, "_try_send_welcome_notification", new_callable=AsyncMock)
async def test_create_empty_preferred_shift_stored_as_null(mock_notify):
    repo = _make_repo()
    service = UserService(repo)

    resp = await service.create_user(_base_create(preferred_shift=""))

    saved_user = repo.save.call_args[0][0]
    assert saved_user.preferred_shift is None
    assert resp.preferred_shift is None


@pytest.mark.asyncio
@patch.object(UserService, "_try_send_welcome_notification", new_callable=AsyncMock)
async def test_create_persists_payroll_fields(mock_notify):
    """Regression: payroll ids used to be accepted by the schema but dropped."""
    repo = _make_repo()
    service = UserService(repo)

    await service.create_user(
        _base_create(payroll_employee_id="123", payroll_ylm_code="45"),
    )

    saved_user = repo.save.call_args[0][0]
    assert saved_user.payroll_employee_id == "123"
    assert saved_user.payroll_ylm_code == "45"


@pytest.mark.asyncio
async def test_update_empty_string_clears_preferred_shift():
    repo = _make_repo()
    existing = User(
        phone_number="972521234567",
        first_name="ישראל",
        last_name="ישראלי",
        roles=["AHMASH"],
        preferred_shift="morning",
    )
    existing.id = uuid.uuid4()
    existing.created_at = datetime(2026, 7, 4, 12, 0, 0)
    existing.is_active = True
    existing.min_total_shifts = 0
    existing.min_night_shifts = 0
    existing.min_evening_shifts = 0
    repo.get_by_id.return_value = existing
    service = UserService(repo)

    resp = await service.update_user(existing.id, UserUpdate(preferred_shift=""))

    assert existing.preferred_shift is None
    assert resp.preferred_shift is None


@pytest.mark.asyncio
async def test_update_sets_preferred_shift():
    repo = _make_repo()
    existing = User(
        phone_number="972521234567",
        first_name="ישראל",
        last_name="ישראלי",
        roles=["AHMASH"],
    )
    existing.id = uuid.uuid4()
    existing.created_at = datetime(2026, 7, 4, 12, 0, 0)
    existing.is_active = True
    existing.min_total_shifts = 0
    existing.min_night_shifts = 0
    existing.min_evening_shifts = 0
    repo.get_by_id.return_value = existing
    service = UserService(repo)

    resp = await service.update_user(
        existing.id, UserUpdate(preferred_shift="afternoon"),
    )

    assert existing.preferred_shift == "afternoon"
    assert resp.preferred_shift == "afternoon"
