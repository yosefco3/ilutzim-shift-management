"""
WeekProfileService — binds weeks to activation profiles (part B).

A week is built from exactly one profile. The binding is stored explicitly in
``week_profile_assignments``; a week with no row falls back to the **default**
profile (``is_default`` — the seeded "שגרה"). This keeps the board non-empty for
every week without forcing the manager to pick one up front.
"""

import logging
import uuid

from app.exceptions import ProfileNotFoundException, WeekNotFoundException
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.repositories.week_profile_repository import (
    WeekProfileRepository,
)

logger = logging.getLogger("ilutzim")


class WeekProfileService:
    """Resolve and set the profile a week is built from."""

    def __init__(
        self,
        week_profile_repo: WeekProfileRepository,
        profile_repo: ProfileRepository,
        week_repo: ScheduleWeekRepository,
    ) -> None:
        self._repo = week_profile_repo
        self._profile_repo = profile_repo
        self._week_repo = week_repo

    async def get_effective_profile(
        self, week_id: uuid.UUID
    ) -> tuple[ActivationProfile, bool]:
        """Return ``(profile, is_default_fallback)`` for a week.

        Uses the explicit assignment when present; otherwise the default profile.
        ``is_default_fallback`` is True when no explicit assignment exists.

        The board must stay non-empty for *every* week (that is the whole point of
        the fallback). So when no profile carries the ``is_default`` flag — a state
        the app should never reach, but can if the default was deleted or its flag
        lost — we fall back to the first profile by display order rather than
        breaking the board. Only a genuinely empty profile table raises.
        """
        assignment = await self._repo.get_by_week(week_id)
        if assignment is not None:
            profile = await self._profile_repo.get_by_id(assignment.profile_id)
            if profile is not None:
                return profile, False
        default = await self._profile_repo.get_default()
        if default is not None:
            return default, True
        # No flagged default — degrade gracefully to any existing profile.
        first = await self._profile_repo.get_first_ordered()
        if first is None:
            raise ProfileNotFoundException()
        return first, True

    async def set_profile(
        self, week_id: uuid.UUID, profile_id: uuid.UUID
    ) -> WeekProfileAssignment:
        """Assign ``profile_id`` to ``week_id`` (replacing any existing binding)."""
        if await self._week_repo.get_by_id(week_id) is None:
            raise WeekNotFoundException()
        if await self._profile_repo.get_by_id(profile_id) is None:
            raise ProfileNotFoundException()
        assignment = await self._repo.upsert(week_id, profile_id)
        logger.info("Assigned profile %s to week %s", profile_id, week_id)
        return assignment
