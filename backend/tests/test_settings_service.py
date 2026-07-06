"""Tests for SettingsService.

The service must bridge the controller's {key, value, description} list contract
to the repository's real API (get_all_settings/get/set on setting_key/setting_value).
The previous implementation called non-existent repo methods (get_all/upsert/get_by_key)
and fields (row.key/row.value), so every /admin/settings call 500'd.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exceptions import ValidationException
from app.schemas.common_schemas import SettingsUpdateRequest
from app.services.settings_service import SETTINGS_DEFAULTS, SettingsService


def _row(key, value, description=None):
    r = MagicMock()
    r.setting_key = key
    r.setting_value = value
    r.description = description
    return r


@pytest.mark.asyncio
async def test_get_settings_returns_one_item_per_default_key():
    """With no DB rows, every SETTINGS_DEFAULTS key is returned at its default."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    items = await svc.get_settings()

    keys = {i.key for i in items}
    assert keys == set(SETTINGS_DEFAULTS.keys())
    # Order follows SETTINGS_DEFAULTS
    assert [i.key for i in items] == list(SETTINGS_DEFAULTS.keys())


@pytest.mark.asyncio
async def test_constraint_rule_thresholds_present_with_defaults():
    """The constraint-rule thresholds are exposed at their defaults."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    items = {i.key: i.value for i in await svc.get_settings()}

    assert items["min_shifts_per_guard"] == "5"
    assert items["min_nights"] == "2"
    assert items["min_evenings"] == "2"
    assert items["max_consecutive_days"] == "6"


@pytest.mark.asyncio
async def test_auto_open_lock_placeholders_present():
    """The cron placeholder fields exist (bools serialized as 'true'/'false')."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    items = {i.key: i.value for i in await svc.get_settings()}

    assert items["auto_open_enabled"] == "false"
    assert items["auto_open_weekday"] == "thursday"
    assert items["auto_lock_enabled"] == "false"
    assert items["auto_lock_time"] == "20:00"


@pytest.mark.asyncio
async def test_db_row_overrides_default():
    """A DB row's value/description override the default for that key."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = [_row("min_nights", "9", "לילות")]

    svc = SettingsService(repo)
    items = {i.key: i for i in await svc.get_settings()}

    assert items["min_nights"].value == "9"
    assert items["min_nights"].description == "לילות"


@pytest.mark.asyncio
async def test_bool_default_serialized_lowercase():
    """Boolean defaults serialize to 'true'/'false', not 'True'/'False'."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    items = {i.key: i for i in await svc.get_settings()}

    assert items["notifications_enabled"].value == "true"


@pytest.mark.asyncio
async def test_update_settings_persists_and_returns_full_list():
    """update_settings writes each key via repo.set and returns the merged list."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    result = await svc.update_settings(
        SettingsUpdateRequest(settings={"min_nights": "3"})
    )

    repo.set.assert_awaited_once_with("min_nights", "3")
    assert {i.key for i in result} == set(SETTINGS_DEFAULTS.keys())


@pytest.mark.asyncio
async def test_update_settings_rejects_unknown_key():
    """Unknown keys raise ValidationException and are not written."""
    repo = AsyncMock()

    svc = SettingsService(repo)
    with pytest.raises(ValidationException):
        await svc.update_settings(SettingsUpdateRequest(settings={"nope": "1"}))
    repo.set.assert_not_awaited()


def _both_auto(open_time, lock_time, *, open_day="thursday", lock_day="thursday",
               open_on=True, lock_on=True):
    """A full auto-open/lock settings payload for the window-validation tests."""
    return SettingsUpdateRequest(settings={
        "auto_open_enabled": "true" if open_on else "false",
        "auto_open_weekday": open_day,
        "auto_open_time": open_time,
        "auto_lock_enabled": "true" if lock_on else "false",
        "auto_lock_weekday": lock_day,
        "auto_lock_time": lock_time,
    })


@pytest.mark.asyncio
async def test_update_settings_rejects_lock_before_open_same_day():
    """Auto-lock at/before auto-open on the same day is rejected (no write)."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    with pytest.raises(ValidationException):
        await svc.update_settings(_both_auto("19:00", "18:00"))
    repo.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_settings_rejects_lock_equal_open():
    """An auto-lock exactly equal to auto-open is not 'after' — rejected."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    with pytest.raises(ValidationException):
        await svc.update_settings(_both_auto("19:00", "19:00"))
    repo.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_settings_accepts_lock_after_open_same_day():
    """Auto-lock after auto-open on the same day is accepted and persisted."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    await svc.update_settings(_both_auto("19:00", "19:30"))
    assert repo.set.await_count == 6


@pytest.mark.asyncio
async def test_update_settings_lock_weekday_after_open_weekday_accepted():
    """A later weekday wins even when its clock time is earlier in the day."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    # Thursday 20:00 → Saturday 08:00: later day, earlier time — still valid.
    await svc.update_settings(
        _both_auto("20:00", "08:00", open_day="thursday", lock_day="saturday")
    )
    assert repo.set.await_count == 6


@pytest.mark.asyncio
async def test_update_settings_skips_window_check_when_lock_disabled():
    """With auto-lock off, an 'earlier' lock time doesn't block the save."""
    repo = AsyncMock()
    repo.get_all_settings.return_value = []

    svc = SettingsService(repo)
    await svc.update_settings(_both_auto("19:00", "18:00", lock_on=False))
    assert repo.set.await_count == 6


@pytest.mark.asyncio
async def test_get_setting_falls_back_to_default():
    """get_setting returns the DB value when present, else the default."""
    repo = AsyncMock()
    repo.get.return_value = None
    svc = SettingsService(repo)
    assert await svc.get_setting("min_nights") == SETTINGS_DEFAULTS["min_nights"]

    repo.get.return_value = "07:00-16:30"
    assert await svc.get_setting("shift_default_morning") == "07:00-16:30"
