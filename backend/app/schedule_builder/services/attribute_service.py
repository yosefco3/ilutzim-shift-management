"""
AttributeService — business logic for the configurable requirement-attribute
vocabulary (part B).

CRUD + idempotent seeding of the default vocabulary. Request-path methods only
flush (the ``get_pool`` request dependency commits); ``seed_default_attributes``
runs at startup with its own session and commits itself.
"""

import logging
import uuid

from app.exceptions import (
    AttributeKeyConflictException,
    AttributeNotFoundException,
)
from app.schedule_builder.models.requirement_attribute import RequirementAttribute
from app.schedule_builder.repositories.attribute_repository import AttributeRepository

logger = logging.getLogger("ilutzim")

# Default guard-characterization vocabulary (אפיון המאבטחים). Still configurable
# from the UI — these are only the seed defaults for a fresh install.
DEFAULT_ATTRIBUTES: list[tuple[str, str]] = [
    ("ahmash", 'אחמ"ש'),
    ("armed", "חמוש"),
    ("patrol_vehicle", "רכב סיור"),
]


class AttributeService:
    """Orchestrates the requirement-attribute vocabulary lifecycle."""

    def __init__(self, attribute_repo: AttributeRepository) -> None:
        self._repo = attribute_repo

    async def list_attributes(self) -> list[RequirementAttribute]:
        """Return all attributes, ordered for display."""
        return await self._repo.get_all_ordered()

    async def create_attribute(self, key: str, label: str) -> RequirementAttribute:
        """Create a new attribute. Raises on duplicate key."""
        if await self._repo.get_by_key(key) is not None:
            raise AttributeKeyConflictException()
        order = await self._repo.max_display_order() + 1
        attr = RequirementAttribute(key=key, label=label, display_order=order)
        created = await self._repo.save(attr)
        logger.info("Created requirement attribute %s (id=%s)", key, created.id)
        return created

    async def update_attribute(
        self,
        attribute_id: uuid.UUID,
        key: str | None = None,
        label: str | None = None,
    ) -> RequirementAttribute:
        """Update key/label. Only provided (non-None) fields change."""
        attr = await self._get_or_raise(attribute_id)
        fields: dict = {}
        if key is not None and key != attr.key:
            if await self._repo.get_by_key(key) is not None:
                raise AttributeKeyConflictException()
            fields["key"] = key
        if label is not None:
            fields["label"] = label
        if not fields:
            return attr
        updated = await self._repo.update(attribute_id, **fields)
        logger.info("Updated requirement attribute %s", attribute_id)
        return updated

    async def delete_attribute(self, attribute_id: uuid.UUID) -> None:
        """Delete an attribute. (Positions referencing it keep the soft key.)"""
        await self._get_or_raise(attribute_id)
        await self._repo.delete(attribute_id)
        logger.info("Deleted requirement attribute %s", attribute_id)

    async def seed_default_attributes(self) -> None:
        """Idempotently ensure the default vocabulary exists.

        If any attribute already exists, this is a no-op. Runs at startup with
        its own session, so it commits itself.
        """
        existing = await self._repo.count()
        if existing > 0:
            logger.debug("Attributes already exist (%d); skipping seed.", existing)
            return
        for order, (key, label) in enumerate(DEFAULT_ATTRIBUTES):
            self._repo.session.add(
                RequirementAttribute(key=key, label=label, display_order=order)
            )
        await self._repo.session.commit()
        logger.info("Seeded %d default requirement attributes", len(DEFAULT_ATTRIBUTES))

    async def _get_or_raise(self, attribute_id: uuid.UUID) -> RequirementAttribute:
        attr = await self._repo.get_by_id(attribute_id)
        if attr is None:
            raise AttributeNotFoundException()
        return attr
