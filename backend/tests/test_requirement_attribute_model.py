"""
Tests for the RequirementAttribute model (part B — schedule builder).
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.schedule_builder.models.requirement_attribute import RequirementAttribute


class TestRequirementAttributeModel:
    async def test_create_with_defaults(self, db_session):
        attr = RequirementAttribute(key="armed", label="חמוש")
        db_session.add(attr)
        await db_session.flush()
        await db_session.refresh(attr)

        assert isinstance(attr.id, uuid.UUID)
        assert attr.key == "armed"
        assert attr.label == "חמוש"
        assert attr.display_order == 0

    async def test_key_is_unique(self, db_session):
        db_session.add(RequirementAttribute(key="armed", label="חמוש"))
        await db_session.flush()
        db_session.add(RequirementAttribute(key="armed", label="חמוש שוב"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    def test_table_name(self):
        assert RequirementAttribute.__tablename__ == "requirement_attributes"
