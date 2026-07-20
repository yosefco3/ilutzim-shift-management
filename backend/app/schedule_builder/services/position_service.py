"""
PositionService — business logic for positions (part B).

CRUD scoped to a profile. The positions screen is "within a selected profile",
so list/create operate by ``profile_id``; update/delete operate by position id.
Request-path methods only flush (the ``get_pool`` request dependency commits).
"""

import logging
import uuid

from app.exceptions import (
    PositionBulkMismatchException,
    PositionNotFoundException,
    PositionReorderMismatchException,
    ProfileNotFoundException,
)
from app.schedule_builder.models.position import Position
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository

logger = logging.getLogger("ilutzim")


class PositionService:
    """Orchestrates position lifecycle within a profile."""

    def __init__(
        self,
        position_repo: PositionRepository,
        profile_repo: ProfileRepository | None = None,
    ) -> None:
        self._repo = position_repo
        # Used only by ``copy_position`` to validate the *target* profile exists.
        # Optional so callers that never copy can construct a bare service; falls
        # back to a repo on the same session when not injected.
        self._profile_repo = profile_repo or ProfileRepository(position_repo.session)

    async def list_positions(self, profile_id: uuid.UUID) -> list[Position]:
        """Return a profile's positions, ordered for display."""
        return await self._repo.get_by_profile(profile_id)

    async def get_position(self, position_id: uuid.UUID) -> Position:
        """Return a single position or raise PositionNotFoundException."""
        return await self._get_or_raise(position_id)

    async def create_position(
        self,
        profile_id: uuid.UUID,
        name: str,
        day_schedules: dict | None = None,
        required_attributes: list | None = None,
        is_event: bool = False,
        event_required_count: int | None = None,
    ) -> Position:
        """Create a position. display_order is appended within the profile."""
        order = await self._repo.max_display_order_in_profile(profile_id) + 1
        position = Position(
            profile_id=profile_id,
            name=name,
            day_schedules=day_schedules or {},
            required_attributes=required_attributes or [],
            is_event=bool(is_event),
            # The fixed count is event-only — a normal position never carries one.
            event_required_count=event_required_count if is_event else None,
            display_order=order,
        )
        created = await self._repo.save(position)
        logger.info("Created position %s (profile=%s)", created.id, profile_id)
        return created

    async def update_position(
        self,
        position_id: uuid.UUID,
        name: str | None = None,
        day_schedules: dict | None = None,
        required_attributes: list | None = None,
        is_event: bool | None = None,
        event_required_count: int | None = None,
    ) -> Position:
        """Update a position. Only provided (non-None) fields change."""
        await self._get_or_raise(position_id)
        fields: dict = {}
        if name is not None:
            fields["name"] = name
        if day_schedules is not None:
            fields["day_schedules"] = day_schedules
        if required_attributes is not None:
            fields["required_attributes"] = required_attributes
        if is_event is not None:
            fields["is_event"] = bool(is_event)
            # The count is event-only and always sent alongside is_event by the
            # UI, so treat it as authoritative here: take the provided count when
            # it's an event, else clear it. This is also how it's cleared back to
            # "unlimited" (uncheck the fixed-count box → event_required_count None).
            fields["event_required_count"] = (
                event_required_count if bool(is_event) else None
            )
        elif event_required_count is not None:
            # Sparse update touching only the count (is_event unchanged).
            fields["event_required_count"] = event_required_count
        if not fields:
            return await self._get_or_raise(position_id)
        updated = await self._repo.update(position_id, **fields)
        logger.info("Updated position %s", position_id)
        return updated

    async def reorder_positions(
        self, profile_id: uuid.UUID, ordered_ids: list[uuid.UUID]
    ) -> list[Position]:
        """Persist a new display order for a profile's positions (drag-and-drop).

        ``ordered_ids`` must be an **exact permutation** of the profile's
        positions — assigns ``display_order`` = list index. The within-band
        constraint is enforced by the UI; here we only require a full, valid
        permutation (the board re-groups by band on render regardless of order).

        Raises ``PositionReorderMismatchException`` when the id set does not match
        the profile's positions (missing / foreign / extra id).
        """
        positions = await self._repo.get_by_profile(profile_id)
        existing_ids = {p.id for p in positions}
        if set(ordered_ids) != existing_ids:
            raise PositionReorderMismatchException()
        for order, position_id in enumerate(ordered_ids):
            await self._repo.set_display_order(position_id, order)
        logger.info(
            "Reordered %d positions in profile %s", len(ordered_ids), profile_id
        )
        return await self._repo.get_by_profile(profile_id)

    async def bulk_update_day_schedules(
        self,
        profile_id: uuid.UUID,
        items: list[tuple[uuid.UUID, dict]],
    ) -> list[Position]:
        """Atomically set ``day_schedules`` for many of a profile's positions.

        Each item is a ``(position_id, day_schedules)`` pair. ``day_schedules``
        replaces the position's map wholesale (``{}`` closes it for the week —
        [EDGE D3]). Positions NOT mentioned are untouched [EDGE C1].

        The whole body is validated BEFORE any mutation, so a failure leaves
        nothing written (all-or-nothing — [EDGE N1]; the request dependency
        commits once at the end). Raises ``PositionBulkMismatchException`` (409)
        — with the offending ids in the message — if any ``position_id`` does not
        belong to the profile or repeats within ``items`` [EDGE C2].
        """
        if await self._profile_repo.get_by_id(profile_id) is None:
            raise ProfileNotFoundException()
        positions = await self._repo.get_by_profile(profile_id)
        existing_ids = {p.id for p in positions}

        # Collect offending ids (unknown / foreign / duplicate) in encounter
        # order; the loop must finish before the first write.
        requested_ids = [pid for pid, _ in items]
        offending: list[uuid.UUID] = []
        seen: set[uuid.UUID] = set()
        for pid in requested_ids:
            if pid not in existing_ids or pid in seen:
                offending.append(pid)
            seen.add(pid)
        if offending:
            unique = list(dict.fromkeys(offending))  # dedupe, keep order
            bad = ", ".join(str(pid) for pid in unique)
            raise PositionBulkMismatchException(
                f"עמדות לא תואמות לפרופיל: {bad}"
            )

        for pid, day_schedules in items:
            await self._repo.update(pid, day_schedules=day_schedules)
        logger.info(
            "Bulk-set day_schedules for %d positions in profile %s",
            len(items), profile_id,
        )
        return await self._repo.get_by_profile(profile_id)

    async def delete_position(self, position_id: uuid.UUID) -> None:
        """Delete a position. (A profile may be left with no positions.)"""
        await self._get_or_raise(position_id)
        await self._repo.delete(position_id)
        logger.info("Deleted position %s", position_id)

    async def copy_position(
        self, position_id: uuid.UUID, target_profile_id: uuid.UUID
    ) -> Position:
        """Deep-copy a position into another profile (drag-and-drop in the UI).

        The copy is independent: its JSON fields are copied by value (no shared
        reference with the source), so editing/deleting either side never affects
        the other. ``display_order`` is appended within the *target* profile.
        Copying onto the source's own profile is allowed (acts as a duplicate).

        Raises ``PositionNotFoundException`` if the source is missing, or
        ``ProfileNotFoundException`` if the target profile does not exist.
        """
        src = await self._get_or_raise(position_id)
        if await self._profile_repo.get_by_id(target_profile_id) is None:
            raise ProfileNotFoundException()
        order = (
            await self._repo.max_display_order_in_profile(target_profile_id) + 1
        )
        copy = Position(
            profile_id=target_profile_id,
            name=src.name,
            day_schedules=dict(src.day_schedules or {}),
            required_attributes=list(src.required_attributes or []),
            is_event=bool(src.is_event),
            event_required_count=src.event_required_count,
            display_order=order,
        )
        created = await self._repo.save(copy)
        logger.info(
            "Copied position %s -> profile %s (new %s)",
            position_id, target_profile_id, created.id,
        )
        return created

    async def _get_or_raise(self, position_id: uuid.UUID) -> Position:
        position = await self._repo.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundException()
        return position
