"""
ProfileRepository — data access for activation profiles (part B).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import BaseRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position


class ProfileRepository(BaseRepository[ActivationProfile]):
    """Data-access operations for ActivationProfile entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ActivationProfile)

    async def get_all_ordered(self) -> list[ActivationProfile]:
        """Return all profiles ordered by display_order, then created_at.

        Each returned profile carries a transient ``position_count`` attribute
        (the number of positions owning it) for display in the management UI.
        """
        count_subq = (
            select(func.count(Position.id))
            .where(Position.profile_id == ActivationProfile.id)
            .correlate(ActivationProfile)
            .scalar_subquery()
        )
        stmt = select(ActivationProfile, count_subq).order_by(
            ActivationProfile.display_order.asc(),
            ActivationProfile.created_at.asc(),
        )
        result = await self.session.execute(stmt)
        profiles: list[ActivationProfile] = []
        for profile, count in result.all():
            profile.position_count = count
            profiles.append(profile)
        return profiles

    async def get_default(self) -> ActivationProfile | None:
        """Return the profile flagged is_default, if any."""
        stmt = select(self.model_class).where(ActivationProfile.is_default.is_(True))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_first_ordered(self) -> ActivationProfile | None:
        """Return the first profile by display_order (fallback when no default)."""
        stmt = select(self.model_class).order_by(
            ActivationProfile.display_order.asc(),
            ActivationProfile.created_at.asc(),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count(self) -> int:
        """Return the total number of profiles."""
        result = await self.session.execute(select(func.count(ActivationProfile.id)))
        return result.scalar()

    async def max_display_order(self) -> int:
        """Return the highest display_order in use (0 if no profiles)."""
        result = await self.session.execute(
            select(func.coalesce(func.max(ActivationProfile.display_order), 0))
        )
        return result.scalar() or 0
