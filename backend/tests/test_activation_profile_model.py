"""
Tests for the ActivationProfile model (part B — schedule builder).
"""

import uuid

from app.schedule_builder.models.activation_profile import ActivationProfile


class TestActivationProfileModel:
    async def test_create_minimal(self, db_session):
        """A profile with only a name persists, with correct defaults."""
        profile = ActivationProfile(name="שגרה")
        db_session.add(profile)
        await db_session.flush()
        await db_session.refresh(profile)

        assert isinstance(profile.id, uuid.UUID)
        assert profile.name == "שגרה"
        assert profile.kind is None
        assert profile.description is None
        assert profile.is_default is False
        assert profile.display_order == 0
        assert profile.created_at is not None

    async def test_optional_fields_nullable(self, db_session):
        """kind and description accept None and explicit values."""
        profile = ActivationProfile(
            name="חג סוכות",
            kind="חג",
            description="עמדות מיוחדות לחג",
            is_default=False,
            display_order=3,
        )
        db_session.add(profile)
        await db_session.flush()
        await db_session.refresh(profile)

        assert profile.kind == "חג"
        assert profile.description == "עמדות מיוחדות לחג"
        assert profile.display_order == 3

    async def test_round_trip(self, db_session):
        """A persisted profile can be re-fetched by id."""
        profile = ActivationProfile(name="אירוע ספורט", is_default=True)
        db_session.add(profile)
        await db_session.flush()
        pid = profile.id

        fetched = await db_session.get(ActivationProfile, pid)
        assert fetched is not None
        assert fetched.name == "אירוע ספורט"
        assert fetched.is_default is True

    def test_table_name(self):
        assert ActivationProfile.__tablename__ == "activation_profiles"
