"""
Typed accessor for the attendance settings block.

The raw keys live in ``SETTINGS_DEFAULTS`` (part A — ``SettingsService``);
this module turns them into one frozen, validated ``AttendanceConfig`` object
so every attendance layer (bot punch flow, comparison engine, alerts, payroll
export) reads the same parsed values from a single place.

Parsing is tolerant, matching the automation-settings convention: a bad stored
value (e.g. text in a numeric field) logs a warning and falls back to the
default instead of crashing a scheduler job or a punch.
"""

import logging
from dataclasses import dataclass

from app.services.automation_settings import as_bool
from app.services.settings_service import SETTINGS_DEFAULTS, SettingsService

logger = logging.getLogger("ilutzim")


@dataclass(frozen=True)
class AttendanceConfig:
    """Parsed attendance settings — the single consumer-facing shape."""

    grace_minutes: int
    big_gap_minutes: int
    site_lat: float | None
    site_lng: float | None
    site_radius_m: int
    admin_alerts_enabled: bool
    admin_chat_id: str
    company_name: str
    # Alert thresholds (0 = that check is disabled). Defaults keep every
    # existing AttendanceConfig(...) construction valid.
    long_shift_hours: int = 12
    min_rest_hours: int = 8

    @property
    def site_configured(self) -> bool:
        """True when both site coordinates are set → radius checks apply."""
        return self.site_lat is not None and self.site_lng is not None


def _as_int(value: object, key: str) -> int:
    """Parse a non-negative int; bad/negative input → default + warning."""
    default = int(SETTINGS_DEFAULTS[key])
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        logger.warning("Attendance setting %s=%r is not a number — using %s", key, value, default)
        return default
    if parsed < 0:
        logger.warning("Attendance setting %s=%r is negative — using %s", key, value, default)
        return default
    return parsed


def _as_float_or_none(value: object, key: str) -> float | None:
    """Parse an optional float; blank means "not configured" (None)."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        logger.warning("Attendance setting %s=%r is not a number — treating as unset", key, value)
        return None


async def get_attendance_config(settings_service: SettingsService) -> AttendanceConfig:
    """Read and parse the whole attendance settings block."""

    async def raw(key: str) -> object:
        return await settings_service.get_setting(key)

    return AttendanceConfig(
        grace_minutes=_as_int(await raw("attendance_grace_minutes"), "attendance_grace_minutes"),
        big_gap_minutes=_as_int(
            await raw("attendance_big_gap_minutes"), "attendance_big_gap_minutes"
        ),
        site_lat=_as_float_or_none(await raw("attendance_site_lat"), "attendance_site_lat"),
        site_lng=_as_float_or_none(await raw("attendance_site_lng"), "attendance_site_lng"),
        site_radius_m=_as_int(
            await raw("attendance_site_radius_m"), "attendance_site_radius_m"
        ),
        admin_alerts_enabled=as_bool(await raw("attendance_admin_alerts_enabled")),
        admin_chat_id=str(await raw("attendance_admin_chat_id") or "").strip(),
        company_name=str(await raw("company_name") or "").strip(),
        long_shift_hours=_as_int(
            await raw("attendance_long_shift_hours"), "attendance_long_shift_hours"
        ),
        min_rest_hours=_as_int(
            await raw("attendance_min_rest_hours"), "attendance_min_rest_hours"
        ),
    )
