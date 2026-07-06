"""
ProfileService — business logic for activation profiles (part B).

CRUD + duplicate (the core workflow) + idempotent seeding of the default
"שגרה" profile. Request-path methods only flush (the request dependency
``get_pool`` commits); ``seed_default_profile`` runs at startup with its own
session and commits itself.
"""

import logging
import uuid

from app.exceptions import ProfileDeleteBlockedException, ProfileNotFoundException
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.repositories.assignment_repository import AssignmentRepository
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository

logger = logging.getLogger("ilutzim")

DEFAULT_PROFILE_NAME = "שגרה"


class ProfileService:
    """Orchestrates activation-profile lifecycle."""

    def __init__(
        self,
        profile_repo: ProfileRepository,
        position_repo: PositionRepository | None = None,
        assignment_repo: AssignmentRepository | None = None,
    ) -> None:
        self._repo = profile_repo
        # Used for deep-copying positions on duplicate. Optional so startup
        # seeding (which never duplicates) can construct a bare service. Falls
        # back to a repo on the same session when not injected.
        self._position_repo = position_repo or PositionRepository(profile_repo.session)
        # Used to compute how many weeks a delete would wipe. Same optional
        # pattern — falls back to a repo on the same session.
        self._assignment_repo = assignment_repo or AssignmentRepository(
            profile_repo.session
        )

    async def list_profiles(self) -> list[ActivationProfile]:
        """Return all profiles, ordered for display."""
        return await self._repo.get_all_ordered()

    async def get_profile(self, profile_id: uuid.UUID) -> ActivationProfile:
        """Return a single profile or raise ProfileNotFoundException."""
        return await self._get_or_raise(profile_id)

    async def create_profile(
        self,
        name: str,
        kind: str | None = None,
        description: str | None = None,
    ) -> ActivationProfile:
        """Create a new profile. display_order is appended at the end."""
        order = await self._repo.max_display_order() + 1
        profile = ActivationProfile(
            name=name,
            kind=kind,
            description=description,
            is_default=False,
            display_order=order,
        )
        created = await self._repo.save(profile)
        logger.info("Created activation profile %s (id=%s)", name, created.id)
        return created

    async def rename_profile(
        self,
        profile_id: uuid.UUID,
        name: str | None = None,
        kind: str | None = None,
        description: str | None = None,
    ) -> ActivationProfile:
        """Update meta fields (name/kind/description). Never touches is_default.

        Only the fields explicitly provided (not None) are changed.
        """
        profile = await self._get_or_raise(profile_id)
        fields: dict = {}
        if name is not None:
            fields["name"] = name
        if kind is not None:
            fields["kind"] = kind
        if description is not None:
            fields["description"] = description
        if not fields:
            return profile
        updated = await self._repo.update(profile_id, **fields)
        logger.info("Updated activation profile %s", profile_id)
        return updated

    async def set_default_profile(
        self, profile_id: uuid.UUID
    ) -> ActivationProfile:
        """Mark a profile as the default, clearing the flag on any other.

        Exactly one profile is the default (the board falls back to it for weeks
        with no explicit assignment). Idempotent if the target is already default.
        """
        await self._get_or_raise(profile_id)
        current = await self._repo.get_default()
        if current is not None and current.id != profile_id:
            await self._repo.update(current.id, is_default=False)
        updated = await self._repo.update(profile_id, is_default=True)
        logger.info("Set default activation profile %s", profile_id)
        return updated

    async def delete_impact(self, profile_id: uuid.UUID) -> dict:
        """Report what deleting this profile would destroy, so the UI can warn
        before an irreversible cascade wipes real schedules.

        Returns ``{"weeks": int, "assignments": int, "is_last": bool}``:
        ``weeks``/``assignments`` are the schedules that sit on this profile's
        positions and would be cascade-deleted; ``is_last`` mirrors the
        delete guard (the sole remaining profile cannot be deleted).
        """
        await self._get_or_raise(profile_id)
        weeks, assignments = await self._assignment_repo.count_impact_for_profile(
            profile_id
        )
        total = await self._repo.count()
        return {"weeks": weeks, "assignments": assignments, "is_last": total <= 1}

    async def delete_profile(self, profile_id: uuid.UUID) -> None:
        """Delete a profile.

        Guard: at least one profile must always remain (cannot delete the sole
        remaining profile). Deleting the default is allowed as long as other
        profiles exist — but the flag must not be lost, or the board (which falls
        back to the default) would break, so we promote the next profile to
        default. (Positions are removed by cascade once they exist — task 03.)
        """
        target = await self._get_or_raise(profile_id)
        total = await self._repo.count()
        if total <= 1:
            raise ProfileDeleteBlockedException()
        await self._repo.delete(profile_id)
        logger.info("Deleted activation profile %s", profile_id)
        # Deleting the default would leave no default at all — promote the first
        # remaining profile so exactly one default always exists.
        if target.is_default:
            successor = await self._repo.get_first_ordered()
            if successor is not None:
                await self._repo.update(successor.id, is_default=True)
                logger.info("Promoted profile %s to default after delete", successor.id)

    async def duplicate_profile(
        self, profile_id: uuid.UUID, new_name: str | None = None
    ) -> ActivationProfile:
        """Duplicate a profile — the core workflow ("שגרה" → edit → holiday).

        Copies the profile row (never is_default). Positions are deep-copied via
        ``_copy_positions`` — currently a no-op until positions exist (task 03),
        so the extension stays local and this signature is stable.
        """
        src = await self._get_or_raise(profile_id)
        order = await self._repo.max_display_order() + 1
        dst = ActivationProfile(
            name=new_name or f"{src.name} (עותק)",
            kind=src.kind,
            description=src.description,
            is_default=False,
            display_order=order,
        )
        dst = await self._repo.save(dst)
        await self._copy_positions(src, dst)
        logger.info("Duplicated profile %s -> %s", src.id, dst.id)
        return dst

    async def seed_default_profile(self) -> None:
        """Idempotently ensure a default "שגרה" profile exists.

        If any profile already exists, this is a no-op. Runs at startup with its
        own session, so it commits itself.
        """
        existing = await self._repo.count()
        if existing > 0:
            logger.debug("Profiles already exist (%d); skipping seed.", existing)
            return
        profile = ActivationProfile(
            name=DEFAULT_PROFILE_NAME,
            kind=DEFAULT_PROFILE_NAME,
            is_default=True,
            display_order=0,
        )
        await self._repo.save(profile)
        await self._repo.session.commit()
        logger.info("Seeded default activation profile '%s'", DEFAULT_PROFILE_NAME)

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _copy_positions(
        self, src: ActivationProfile, dst: ActivationProfile
    ) -> None:
        """Deep-copy positions from src to dst.

        Each position is recreated under ``dst`` with copies of its JSON fields
        (so the source and copy never share a reference). ``display_order`` is
        preserved. The public ``duplicate_profile`` signature stays unchanged.
        """
        sources = await self._position_repo.get_by_profile(src.id)
        for pos in sources:
            self._position_repo.session.add(
                Position(
                    profile_id=dst.id,
                    name=pos.name,
                    day_schedules=dict(pos.day_schedules or {}),
                    required_attributes=list(pos.required_attributes or []),
                    display_order=pos.display_order,
                )
            )
        await self._position_repo.session.flush()

    async def _get_or_raise(self, profile_id: uuid.UUID) -> ActivationProfile:
        profile = await self._repo.get_by_id(profile_id)
        if profile is None:
            raise ProfileNotFoundException()
        return profile
