"""
SystemSettings repository — application-wide configuration (string PK).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting
from app.logging_config import get_logger

logger = get_logger(__name__)


class SystemSettingsRepository:
    """Data-access operations for SystemSetting entities (string PK)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        """Get a setting value by key. Returns None if not found."""
        result = await self.session.get(SystemSetting, key)
        return result.setting_value if result else None

    async def set(self, key: str, value: str, description: str | None = None) -> SystemSetting:
        """Create or update a setting."""
        existing = await self.session.get(SystemSetting, key)
        if existing is not None:
            existing.setting_value = value
            if description is not None:
                existing.description = description
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        setting = SystemSetting(
            setting_key=key,
            setting_value=value,
            description=description,
        )
        self.session.add(setting)
        await self.session.flush()
        logger.debug("Set system setting: %s", key)
        return setting

    async def get_all_settings(self) -> list[SystemSetting]:
        """Return all settings."""
        stmt = select(SystemSetting)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, key: str) -> bool:
        """Delete a setting by key."""
        setting = await self.session.get(SystemSetting, key)
        if setting is None:
            return False
        await self.session.delete(setting)
        await self.session.flush()
        logger.debug("Deleted system setting: %s", key)
        return True