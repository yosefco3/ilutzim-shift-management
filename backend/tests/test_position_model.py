"""
Tests for the Position model (part B — schedule builder).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position


async def _make_profile(db_session, name="שגרה"):
    profile = ActivationProfile(name=name)
    db_session.add(profile)
    await db_session.flush()
    return profile


class TestPositionModel:
    async def test_create_with_defaults(self, db_session):
        """A position with only the required fields gets empty JSON defaults."""
        profile = await _make_profile(db_session)
        pos = Position(profile_id=profile.id, name="ארנונה")
        db_session.add(pos)
        await db_session.flush()
        await db_session.refresh(pos)

        assert isinstance(pos.id, uuid.UUID)
        assert pos.name == "ארנונה"
        assert pos.day_schedules == {}
        assert pos.required_attributes == []
        assert pos.display_order == 0

    async def test_json_round_trip(self, db_session):
        """Per-day hours and required attributes survive a round trip."""
        profile = await _make_profile(db_session)
        schedules = {
            "0": {"start": "07:30", "end": "15:00"},
            "1": {"start": "07:30", "end": "15:00"},
        }
        pos = Position(
            profile_id=profile.id,
            name="קומה 6",
            day_schedules=schedules,
            required_attributes=["armed", "ahmash"],
            display_order=2,
        )
        db_session.add(pos)
        await db_session.flush()

        fetched = await db_session.get(Position, pos.id)
        assert fetched.day_schedules == schedules
        assert fetched.required_attributes == ["armed", "ahmash"]
        assert fetched.display_order == 2

    async def test_cascade_delete_with_profile(self, db_session):
        """Deleting a profile removes its positions (cascade)."""
        profile = await _make_profile(db_session)
        for i in range(2):
            db_session.add(
                Position(profile_id=profile.id, name=f"עמדה {i}")
            )
        await db_session.flush()

        loaded = await db_session.get(
            ActivationProfile, profile.id, options=[selectinload(ActivationProfile.positions)]
        )
        await db_session.delete(loaded)
        await db_session.flush()

        count = await db_session.scalar(select(func.count(Position.id)))
        assert count == 0

    async def test_positions_ordered_by_display_order(self, db_session):
        """profile.positions comes back ordered by display_order."""
        profile = await _make_profile(db_session)
        db_session.add(Position(profile_id=profile.id, name="ב", display_order=2))
        db_session.add(Position(profile_id=profile.id, name="א", display_order=1))
        await db_session.flush()

        loaded = await db_session.scalar(
            select(ActivationProfile)
            .where(ActivationProfile.id == profile.id)
            .options(selectinload(ActivationProfile.positions))
        )
        names = [p.name for p in loaded.positions]
        assert names == ["א", "ב"]
