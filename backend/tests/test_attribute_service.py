"""
Tests for AttributeService (part B — schedule builder).
"""

import uuid

import pytest

from app.exceptions import (
    AttributeKeyConflictException,
    AttributeNotFoundException,
)
from app.schedule_builder.repositories.attribute_repository import AttributeRepository
from app.schedule_builder.services.attribute_service import (
    DEFAULT_ATTRIBUTES,
    AttributeService,
)


@pytest.fixture
def service(db_session):
    return AttributeService(AttributeRepository(db_session))


class TestCrud:
    async def test_create_then_list_ordered(self, service):
        await service.create_attribute("armed", "חמוש")
        await service.create_attribute("roni", "רוני")
        attrs = await service.list_attributes()

        assert [a.key for a in attrs] == ["armed", "roni"]
        assert attrs[0].display_order < attrs[1].display_order

    async def test_duplicate_key_blocked(self, service):
        await service.create_attribute("armed", "חמוש")
        with pytest.raises(AttributeKeyConflictException):
            await service.create_attribute("armed", "אחר")

    async def test_update_label(self, service):
        attr = await service.create_attribute("armed", "חמוש")
        updated = await service.update_attribute(attr.id, label="נושא נשק")
        assert updated.label == "נושא נשק"
        assert updated.key == "armed"

    async def test_update_to_existing_key_blocked(self, service):
        await service.create_attribute("armed", "חמוש")
        b = await service.create_attribute("roni", "רוני")
        with pytest.raises(AttributeKeyConflictException):
            await service.update_attribute(b.id, key="armed")

    async def test_update_missing_raises(self, service):
        with pytest.raises(AttributeNotFoundException):
            await service.update_attribute(uuid.uuid4(), label="x")

    async def test_delete(self, service):
        attr = await service.create_attribute("armed", "חמוש")
        await service.delete_attribute(attr.id)
        assert await service.list_attributes() == []

    async def test_delete_missing_raises(self, service):
        with pytest.raises(AttributeNotFoundException):
            await service.delete_attribute(uuid.uuid4())


class TestSeed:
    async def test_seed_creates_defaults(self, service):
        await service.seed_default_attributes()
        attrs = await service.list_attributes()
        assert [a.key for a in attrs] == [k for k, _ in DEFAULT_ATTRIBUTES]

    async def test_seed_idempotent(self, service):
        await service.seed_default_attributes()
        await service.seed_default_attributes()
        attrs = await service.list_attributes()
        assert len(attrs) == len(DEFAULT_ATTRIBUTES)
