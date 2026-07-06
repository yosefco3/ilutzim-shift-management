"""
AdminSettingsController — admin endpoints for system settings.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_settings_service, require_admin_role
from app.schemas.common_schemas import SettingItem, SettingsUpdateRequest
from app.services.settings_service import SettingsService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/settings",
    tags=["Admin – Settings"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("", response_model=list[SettingItem])
async def get_settings(
    settings_service: SettingsService = Depends(get_settings_service),
):
    """Get all system settings as [{key, value, description}]."""
    return await settings_service.get_settings()


@router.put("", response_model=list[SettingItem])
async def update_settings(
    data: SettingsUpdateRequest,
    settings_service: SettingsService = Depends(get_settings_service),
):
    """Apply a partial {settings: {key: value}} update; returns the full list."""
    try:
        result = await settings_service.update_settings(data)
    except Exception as e:
        logger.error(f"Settings update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # If any auto-open/lock setting changed, reschedule the cron jobs so the
    # change takes effect immediately (no restart needed). Read the new values
    # through the *same* request session (which sees its own flushed write) and
    # hand them to the scheduler — letting sync_automation_jobs open its own
    # session would read the still-uncommitted-elsewhere previous value and
    # silently reschedule to the OLD time.
    if any(key.startswith(("auto_open", "auto_lock")) for key in data.settings):
        try:
            from app.scheduler import sync_automation_jobs

            auto_open = await settings_service.get_auto_open()
            auto_lock = await settings_service.get_auto_lock()
            await sync_automation_jobs(auto_open=auto_open, auto_lock=auto_lock)
        except Exception as exc:
            logger.warning("Failed to reschedule automation jobs: %s", exc)

    return result