"""
Tests for the auto open/lock settings layer (prompt 05):
  - pure parsers: parse_weekday, parse_hhmm, as_bool
  - SettingsService.get_auto_open / get_auto_lock typed accessors
"""

from unittest.mock import AsyncMock

import pytest

from app.services.automation_settings import as_bool, parse_hhmm, parse_weekday
from app.services.settings_service import SettingsService


# ── parse_weekday ─────────────────────────────────────────────────────────────

def test_parse_weekday_full_name():
    assert parse_weekday("sunday") == "sun"
    assert parse_weekday("Wednesday") == "wed"


def test_parse_weekday_abbreviation_case_insensitive():
    assert parse_weekday("SUN") == "sun"
    assert parse_weekday("thu") == "thu"


def test_parse_weekday_invalid_falls_back():
    assert parse_weekday("notaday") == "sun"
    assert parse_weekday("", default="mon") == "mon"


# ── parse_hhmm ────────────────────────────────────────────────────────────────

def test_parse_hhmm_valid():
    assert parse_hhmm("07:00") == (7, 0)
    assert parse_hhmm("12:30") == (12, 30)
    assert parse_hhmm("23:59") == (23, 59)


def test_parse_hhmm_out_of_range_and_malformed():
    assert parse_hhmm("24:61") == (0, 0)
    assert parse_hhmm("nope") == (0, 0)
    assert parse_hhmm("7") == (0, 0)
    assert parse_hhmm("08:15", default=(9, 9)) == (8, 15)


# ── as_bool ───────────────────────────────────────────────────────────────────

def test_as_bool_variants():
    assert as_bool(True) is True
    assert as_bool("true") is True
    assert as_bool("FALSE") is False
    assert as_bool("1") is True
    assert as_bool("0") is False
    assert as_bool(None) is False
    assert as_bool("garbage", default=True) is True


# ── accessors ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_auto_open_reads_from_db():
    repo = AsyncMock()
    values = {
        "auto_open_enabled": "true",
        "auto_open_weekday": "sunday",
        "auto_open_time": "07:00",
    }
    repo.get.side_effect = lambda key: values.get(key)

    svc = SettingsService(repo)
    result = await svc.get_auto_open()
    assert result == {"enabled": True, "weekday": "sun", "hour": 7, "minute": 0}


@pytest.mark.asyncio
async def test_get_auto_lock_reads_from_db():
    repo = AsyncMock()
    values = {
        "auto_lock_enabled": "true",
        "auto_lock_weekday": "wednesday",
        "auto_lock_time": "12:00",
    }
    repo.get.side_effect = lambda key: values.get(key)

    svc = SettingsService(repo)
    result = await svc.get_auto_lock()
    assert result == {"enabled": True, "weekday": "wed", "hour": 12, "minute": 0}


@pytest.mark.asyncio
async def test_get_auto_open_falls_back_to_defaults():
    """No DB rows → defaults (disabled, thursday 08:00 per SETTINGS_DEFAULTS)."""
    repo = AsyncMock()
    repo.get.return_value = None

    svc = SettingsService(repo)
    result = await svc.get_auto_open()
    assert result["enabled"] is False
    assert result["weekday"] == "thu"
    assert (result["hour"], result["minute"]) == (8, 0)
