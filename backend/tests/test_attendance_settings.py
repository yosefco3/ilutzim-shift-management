"""
Stage 3 / 01 step 2 — attendance settings: defaults, overrides, tolerant parsing.
"""

import pytest

from app.attendance.services.attendance_settings import get_attendance_config
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.settings_service import SETTINGS_DEFAULTS, SettingsService


def _service(db_session) -> SettingsService:
    return SettingsService(SystemSettingsRepository(db_session))


@pytest.mark.asyncio
async def test_defaults_when_nothing_stored(db_session):
    config = await get_attendance_config(_service(db_session))

    assert config.grace_minutes == 15
    assert config.big_gap_minutes == 60
    assert config.site_lat is None
    assert config.site_lng is None
    assert config.site_configured is False
    assert config.site_radius_m == 150
    assert config.admin_alerts_enabled is False
    assert config.admin_chat_id == ""
    assert config.company_name == "ספרא"


@pytest.mark.asyncio
async def test_stored_values_override_defaults(db_session):
    repo = SystemSettingsRepository(db_session)
    await repo.set("attendance_grace_minutes", "20")
    await repo.set("attendance_site_lat", "31.778")
    await repo.set("attendance_site_lng", "35.235")
    await repo.set("attendance_admin_alerts_enabled", "true")
    await repo.set("attendance_admin_chat_id", " 123456 ")
    await repo.set("company_name", "חברה אחרת")
    await db_session.commit()

    config = await get_attendance_config(_service(db_session))
    assert config.grace_minutes == 20
    assert config.site_lat == pytest.approx(31.778)
    assert config.site_lng == pytest.approx(35.235)
    assert config.site_configured is True
    assert config.admin_alerts_enabled is True
    assert config.admin_chat_id == "123456"
    assert config.company_name == "חברה אחרת"


@pytest.mark.asyncio
async def test_bad_values_fall_back_without_crashing(db_session):
    repo = SystemSettingsRepository(db_session)
    await repo.set("attendance_grace_minutes", "לא מספר")
    await repo.set("attendance_big_gap_minutes", "-5")
    await repo.set("attendance_site_lat", "abc")
    await repo.set("attendance_site_lng", "35.2")
    await db_session.commit()

    config = await get_attendance_config(_service(db_session))
    assert config.grace_minutes == 15          # text → default
    assert config.big_gap_minutes == 60        # negative → default
    assert config.site_lat is None             # unparsable → unset
    assert config.site_configured is False     # one missing coordinate → no geofence


@pytest.mark.asyncio
async def test_attendance_keys_are_known_settings(db_session):
    """The keys exist in SETTINGS_DEFAULTS so PUT /admin/settings accepts them."""
    for key in [
        "attendance_grace_minutes",
        "attendance_big_gap_minutes",
        "attendance_site_lat",
        "attendance_site_lng",
        "attendance_site_radius_m",
        "attendance_admin_alerts_enabled",
        "attendance_admin_chat_id",
        "company_name",
    ]:
        assert key in SETTINGS_DEFAULTS

    # update_settings round-trips through the known-keys validation
    service = _service(db_session)
    from app.schemas.common_schemas import SettingsUpdateRequest

    items = await service.update_settings(
        SettingsUpdateRequest(settings={"attendance_grace_minutes": "25"})
    )
    await db_session.commit()
    by_key = {i.key: i.value for i in items}
    assert by_key["attendance_grace_minutes"] == "25"
