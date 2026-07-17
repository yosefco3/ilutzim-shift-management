"""
SettingsService — business logic for system settings management.
"""

import logging
from typing import Any

from app.exceptions import ValidationException
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.schemas.common_schemas import SettingItem, SettingsUpdateRequest
from app.services.automation_settings import as_bool, parse_hhmm, parse_weekday

logger = logging.getLogger("ilutzim")

# Weekday ordering for comparing the auto-open vs auto-lock moments. Sunday-first,
# matching the admin UI weekday select and the Israeli work week.
_WEEKDAY_ORDER: dict[str, int] = {
    "sunday": 0, "sun": 0,
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2,
    "wednesday": 3, "wed": 3,
    "thursday": 4, "thu": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
}

# Default settings keys and their types
SETTINGS_DEFAULTS: dict[str, Any] = {
    "notifications_enabled": True,
    "shift_default_morning": "07:00-16:30",
    "shift_default_afternoon": "15:00-23:00",
    "shift_default_night": "23:00-07:00",
    # Constraint-rule thresholds — surfaced to the guard form as soft warnings.
    "min_shifts_per_guard": 5,
    "min_nights": 2,
    "min_evenings": 2,
    "max_consecutive_days": 6,
    # Planning-board pool: also list active guards who did NOT submit
    # constraints (at the end, tagged "לא הגיש אילוצים"). OFF hides them from
    # the pool only — existing assignments are never touched.
    "pool_show_unsubmitted": True,
    # Week auto open/lock — placeholder config only (no scheduler wired yet).
    "auto_open_enabled": False,
    "auto_open_weekday": "thursday",
    "auto_open_time": "08:00",
    "auto_lock_enabled": False,
    "auto_lock_weekday": "saturday",
    "auto_lock_time": "20:00",
    # Stage 3 — attendance (app/attendance). Comparison thresholds, the site
    # geofence (blank lat/lng = radius check skipped), admin no-show alerts,
    # and the company name printed on the payroll (י.ל.מ) report headers.
    # Typed parsing lives in app.attendance.services.attendance_settings —
    # this dict only carries defaults (dependency rule: A must not import
    # attendance).
    "attendance_grace_minutes": 15,
    "attendance_big_gap_minutes": 60,
    "attendance_site_lat": "",
    "attendance_site_lng": "",
    "attendance_site_radius_m": 150,
    "attendance_admin_alerts_enabled": False,
    "attendance_admin_chat_id": "",
    # Alert thresholds (0 = that specific check is off).
    "attendance_long_shift_hours": 12,
    "attendance_min_rest_hours": 8,
    "company_name": "ספרא",
    # Procedure-quiz (סד"פ) — pass threshold (percent), quiz size (sampled
    # from a larger bank), and the Claude model id used to generate questions.
    "procedure_pass_threshold": 80,
    "procedure_quiz_size": 7,
    "procedure_ai_model": "claude-opus-4-8",
}


class SettingsService:
    """Orchestrates system-wide settings CRUD."""

    def __init__(self, settings_repo: SystemSettingsRepository) -> None:
        self._settings_repo = settings_repo

    @staticmethod
    def _to_str(value: Any) -> str:
        """Serialize a setting value to the string form stored/returned by the API."""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    async def get_settings(self) -> list[SettingItem]:
        """Return every known setting as {key, value, description}.

        DB rows override the defaults; missing keys fall back to SETTINGS_DEFAULTS.
        Order follows SETTINGS_DEFAULTS so the admin page is stable.
        """
        rows = await self._settings_repo.get_all_settings()
        overrides = {row.setting_key: row for row in rows}
        items: list[SettingItem] = []
        for key, default in SETTINGS_DEFAULTS.items():
            row = overrides.get(key)
            if row is not None:
                items.append(
                    SettingItem(key=key, value=row.setting_value, description=row.description)
                )
            else:
                items.append(SettingItem(key=key, value=self._to_str(default)))
        return items

    async def update_settings(self, req: SettingsUpdateRequest) -> list[SettingItem]:
        """Apply a partial {key: value} update and return the full settings list.

        Validation runs *before* any write, so a rejected save leaves settings
        untouched (no partial application).
        """
        for key in req.settings:
            if key not in SETTINGS_DEFAULTS:
                raise ValidationException(f"Unknown setting: {key}")
        await self._validate_auto_window(req.settings)
        for key, value in req.settings.items():
            await self._settings_repo.set(key, str(value))
            logger.info("Setting updated: %s", key)
        return await self.get_settings()

    async def _effective(self, incoming: dict[str, str], key: str) -> Any:
        """Value for ``key`` from this request if present, else the stored value.

        Lets cross-field validation see the full post-save picture even when the
        request only carries the keys the admin actually changed.
        """
        if key in incoming:
            return incoming[key]
        return await self.get_setting(key)

    async def _auto_moment(self, incoming: dict[str, str], prefix: str) -> tuple[int, int, int]:
        """The (weekday, hour, minute) moment a weekly auto job fires at."""
        weekday = str(await self._effective(incoming, f"{prefix}_weekday"))
        day = _WEEKDAY_ORDER.get(weekday.strip().lower(), 0)
        hour, minute = parse_hhmm(str(await self._effective(incoming, f"{prefix}_time")))
        return (day, hour, minute)

    async def _validate_auto_window(self, incoming: dict[str, str]) -> None:
        """Reject saves where the weekly auto-lock fires at/before the auto-open.

        Only enforced when both auto-open and auto-lock are enabled — if either
        is off, the two moments aren't both active and the order is irrelevant.
        """
        open_enabled = as_bool(await self._effective(incoming, "auto_open_enabled"))
        lock_enabled = as_bool(await self._effective(incoming, "auto_lock_enabled"))
        if not (open_enabled and lock_enabled):
            return
        open_moment = await self._auto_moment(incoming, "auto_open")
        lock_moment = await self._auto_moment(incoming, "auto_lock")
        if lock_moment <= open_moment:
            raise ValidationException(
                "הנעילה האוטומטית חייבת להיות אחרי הפתיחה האוטומטית"
            )

    async def get_setting(self, key: str) -> Any:
        """Get a single setting value (DB value, else the default)."""
        value = await self._settings_repo.get(key)
        if value is not None:
            return value
        return SETTINGS_DEFAULTS.get(key)

    async def _get_auto(self, prefix: str) -> dict:
        """Read a typed {enabled, weekday, hour, minute} block from settings.

        ``prefix`` is "auto_open" or "auto_lock". Values come from the DB (else
        defaults); parsing is tolerant — bad input yields a safe disabled/default
        rather than crashing the scheduler.
        """
        enabled = as_bool(await self.get_setting(f"{prefix}_enabled"))
        weekday = parse_weekday(str(await self.get_setting(f"{prefix}_weekday")))
        hour, minute = parse_hhmm(str(await self.get_setting(f"{prefix}_time")))
        return {"enabled": enabled, "weekday": weekday, "hour": hour, "minute": minute}

    async def get_auto_open(self) -> dict:
        """Typed accessor for the weekly auto-open schedule."""
        return await self._get_auto("auto_open")

    async def get_auto_lock(self) -> dict:
        """Typed accessor for the weekly auto-lock schedule."""
        return await self._get_auto("auto_lock")

    async def get_effective_bot_token(self) -> str:
        """Active Telegram bot token, sourced exclusively from the environment.

        The token is an env var only (TELEGRAM_BOT_TOKEN) — it is never stored in
        or read from the DB. Async kept for a stable call signature in auth paths.
        """
        from app.config import get_settings
        return get_settings().TELEGRAM_BOT_TOKEN or ""

    async def ensure_defaults(self) -> None:
        """Seed any missing default settings on startup."""
        for key, default in SETTINGS_DEFAULTS.items():
            existing = await self._settings_repo.get(key)
            if existing is None:
                await self._settings_repo.set(key, self._to_str(default))
                logger.info(f"Default setting seeded: {key}={default}")