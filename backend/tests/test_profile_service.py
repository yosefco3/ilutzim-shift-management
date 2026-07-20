"""
Tests for ProfileService (part B — schedule builder).
"""

import pytest

from app.exceptions import (
    ProfileBaseUndeletableException,
    ProfileDeleteBlockedException,
    ProfileNotFoundException,
)
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.services.profile_service import (
    DEFAULT_PROFILE_NAME,
    ProfileService,
)


@pytest.fixture
def service(db_session):
    return ProfileService(ProfileRepository(db_session))


class TestCreateAndList:
    async def test_create_then_list_ordered(self, service):
        await service.create_profile("שגרה")
        await service.create_profile("חג", kind="חג", description="ימי חג")
        profiles = await service.list_profiles()

        assert [p.name for p in profiles] == ["שגרה", "חג"]
        assert profiles[1].kind == "חג"
        assert profiles[1].description == "ימי חג"
        # display_order is appended (1, then 2)
        assert profiles[0].display_order < profiles[1].display_order
        assert all(p.is_default is False for p in profiles)

    async def test_get_missing_raises(self, service):
        import uuid

        with pytest.raises(ProfileNotFoundException):
            await service.get_profile(uuid.uuid4())

    async def test_list_reports_position_count(self, service, db_session):
        from app.schedule_builder.models.position import Position

        empty = await service.create_profile("ריק")
        filled = await service.create_profile("מאויש")
        db_session.add_all([
            Position(profile_id=filled.id, name="בניין 1", display_order=1),
            Position(profile_id=filled.id, name="בניין 2", display_order=2),
        ])
        await db_session.flush()

        by_id = {p.id: p for p in await service.list_profiles()}
        assert by_id[empty.id].position_count == 0
        assert by_id[filled.id].position_count == 2


class TestDuplicate:
    async def test_duplicate_copies_meta_not_default(self, service):
        src = await service.create_profile("שגרה", kind="שגרה", description="בסיס")
        dup = await service.duplicate_profile(src.id)

        assert dup.id != src.id
        assert dup.name == "שגרה (עותק)"
        assert dup.kind == "שגרה"
        assert dup.description == "בסיס"
        assert dup.is_default is False
        # A copy is never the base — only the seeded original carries is_base.
        assert dup.is_base is False

    async def test_duplicate_of_base_is_not_base(self, service):
        # Even duplicating THE base yields a normal, deletable copy.
        await service.seed_default_profile()
        base = (await service.list_profiles())[0]
        assert base.is_base is True
        dup = await service.duplicate_profile(base.id)
        assert dup.is_base is False

    async def test_duplicate_with_explicit_name(self, service):
        src = await service.create_profile("שגרה")
        dup = await service.duplicate_profile(src.id, new_name="חג שני")
        assert dup.name == "חג שני"

    async def test_duplicate_deep_copies_positions(self, service, db_session):
        from app.schedule_builder.repositories.position_repository import (
            PositionRepository,
        )
        from app.schedule_builder.services.position_service import PositionService

        positions = PositionService(PositionRepository(db_session))
        src = await service.create_profile("שגרה")
        await positions.create_position(
            src.id, "ארנונה",
            day_schedules={"0": {"start": "07:30", "end": "15:00"}},
            required_attributes=["armed"],
        )
        await positions.create_position(src.id, "קומה 6")

        dup = await service.duplicate_profile(src.id)
        copied = await positions.list_positions(dup.id)
        original = await positions.list_positions(src.id)

        # Two NEW positions under the copy, same content, different ids.
        assert len(copied) == 2
        assert {p.name for p in copied} == {"ארנונה", "קומה 6"}
        assert {p.id for p in copied}.isdisjoint({p.id for p in original})

        # JSON is copied, not shared: mutating the copy must not touch the source.
        arnona_copy = next(p for p in copied if p.name == "ארנונה")
        arnona_copy.day_schedules["0"]["start"] = "09:00"
        arnona_src = next(p for p in original if p.name == "ארנונה")
        assert arnona_src.day_schedules["0"]["start"] == "07:30"


class TestRename:
    async def test_rename_updates_fields_only(self, service):
        p = await service.create_profile("שגרה")
        updated = await service.rename_profile(
            p.id, name="שגרה מעודכנת", kind="שגרה"
        )
        assert updated.name == "שגרה מעודכנת"
        assert updated.kind == "שגרה"

    async def test_rename_does_not_touch_is_default(self, service, db_session):
        # seed creates a default profile
        await service.seed_default_profile()
        default = await ProfileRepository(db_session).get_default()
        assert default is not None
        updated = await service.rename_profile(default.id, name="שגרה ראשית")
        assert updated.is_default is True
        assert updated.name == "שגרה ראשית"


class TestDayLabels:
    """Per-day label map — set/clear/leave via rename_profile, copied on duplicate.

    Validation (key range, length, blank-drop) lives on the schema and is covered
    in test_profile_api.py; the service treats the dict as opaque.
    """

    async def test_rename_sets_and_persists_day_labels(self, service):
        p = await service.create_profile("שגרה")
        updated = await service.rename_profile(p.id, day_labels={"4": "ט׳ באב"})
        assert updated.day_labels == {"4": "ט׳ באב"}
        # Persisted — re-fetch from the DB, not just the returned object.
        assert (await service.get_profile(p.id)).day_labels == {"4": "ט׳ באב"}

    async def test_rename_empty_dict_clears_day_labels(self, service):
        p = await service.create_profile("שגרה")
        await service.rename_profile(p.id, day_labels={"1": "חג", "4": "ט׳ באב"})
        cleared = await service.rename_profile(p.id, day_labels={})
        assert cleared.day_labels == {}
        assert (await service.get_profile(p.id)).day_labels == {}

    async def test_rename_without_day_labels_leaves_them(self, service):
        p = await service.create_profile("שגרה")
        await service.rename_profile(p.id, day_labels={"4": "ט׳ באב"})
        # Rename a different field — day_labels must be untouched (None = unchanged).
        updated = await service.rename_profile(p.id, name="שגרה חדשה")
        assert updated.name == "שגרה חדשה"
        assert updated.day_labels == {"4": "ט׳ באב"}

    async def test_duplicate_copies_day_labels(self, service):
        src = await service.create_profile("שגרה")
        await service.rename_profile(src.id, day_labels={"4": "ט׳ באב", "5": "ערב שבת"})
        dup = await service.duplicate_profile(src.id)

        assert dup.day_labels == {"4": "ט׳ באב", "5": "ערב שבת"}
        # Copied by value — the source keeps its labels and the dicts are distinct.
        refreshed_src = await service.get_profile(src.id)
        assert refreshed_src.day_labels == {"4": "ט׳ באב", "5": "ערב שבת"}
        assert dup.day_labels is not refreshed_src.day_labels


class TestSetDefault:
    async def test_set_default_moves_the_flag(self, service, db_session):
        await service.seed_default_profile()  # creates "שגרה" as default
        original = await ProfileRepository(db_session).get_default()
        other = await service.create_profile("חג")

        updated = await service.set_default_profile(other.id)

        assert updated.is_default is True
        # The previous default has been cleared — exactly one default remains.
        current = await ProfileRepository(db_session).get_default()
        assert current.id == other.id
        refreshed = {p.id: p for p in await service.list_profiles()}
        assert refreshed[original.id].is_default is False

    async def test_set_default_idempotent(self, service, db_session):
        await service.seed_default_profile()
        default = await ProfileRepository(db_session).get_default()
        updated = await service.set_default_profile(default.id)
        assert updated.is_default is True

    async def test_set_default_unknown_raises(self, service):
        import uuid

        with pytest.raises(ProfileNotFoundException):
            await service.set_default_profile(uuid.uuid4())


class TestDelete:
    async def test_delete_normal(self, service):
        await service.create_profile("שגרה")
        target = await service.create_profile("חג")
        await service.delete_profile(target.id)
        remaining = await service.list_profiles()
        assert [p.name for p in remaining] == ["שגרה"]

    async def test_delete_last_profile_blocked(self, service):
        only = await service.create_profile("שגרה")
        with pytest.raises(ProfileDeleteBlockedException):
            await service.delete_profile(only.id)

    async def test_delete_default_promotes_successor(self, service, db_session):
        # Regression: deleting the default must not leave the app with no default
        # (that breaks the board's fallback). The next profile is promoted.
        default = await service.create_profile("שגרה")
        other = await service.create_profile("חג")
        await service.set_default_profile(default.id)
        await service.delete_profile(default.id)
        promoted = await ProfileRepository(db_session).get_default()
        assert promoted is not None
        assert promoted.id == other.id

    async def test_delete_base_blocked(self, service, db_session):
        # The permanent base template (is_base) can never be deleted, even when
        # other profiles exist and even when it is NOT the default.
        await service.seed_default_profile()  # creates the base (is_base=True)
        base = (await service.list_profiles())[0]
        assert base.is_base is True
        other = await service.create_profile("חג")
        await service.set_default_profile(other.id)  # move default off the base
        with pytest.raises(ProfileBaseUndeletableException):
            await service.delete_profile(base.id)
        # Still there.
        names = [p.name for p in await service.list_profiles()]
        assert "שגרה" in names


class TestDeleteImpact:
    async def _assign(self, service, db_session, profile_id):
        """Place one guard on a position of ``profile_id`` for one week."""
        from datetime import date

        from app.constants import WeekStatus
        from app.models.schedule_week import ScheduleWeek
        from app.models.user import User
        from app.repositories.schedule_week_repository import ScheduleWeekRepository
        from app.schedule_builder.models.position import Position
        from app.schedule_builder.repositories.assignment_repository import (
            AssignmentRepository,
        )
        from app.schedule_builder.repositories.position_repository import (
            PositionRepository,
        )
        from app.schedule_builder.services.assignment_service import AssignmentService

        week = ScheduleWeek(
            start_date=date(2099, 1, 5), end_date=date(2099, 1, 11),
            status=WeekStatus.OPEN,
        )
        db_session.add(week)
        pos = Position(
            profile_id=profile_id, name="ארנונה",
            day_schedules={"0": {"start": "07:00", "end": "15:00"}},
        )
        db_session.add(pos)
        user = User(phone_number="0501111111", first_name="נתן", last_name="כהן",
                    roles=[], is_active=True)
        db_session.add(user)
        await db_session.flush()
        svc = AssignmentService(
            AssignmentRepository(db_session),
            ScheduleWeekRepository(db_session),
            PositionRepository(db_session),
        )
        await svc.assign(week.id, pos.id, 0, user.id)

    async def test_impact_counts_weeks_and_assignments(self, service, db_session):
        keep = await service.create_profile("שגרה")  # noqa: F841 — keep >1 profile
        target = await service.create_profile("חג")
        await self._assign(service, db_session, target.id)
        impact = await service.delete_impact(target.id)
        assert impact == {"weeks": 1, "assignments": 1, "is_last": False}

    async def test_impact_zero_when_no_assignments(self, service):
        await service.create_profile("שגרה")
        target = await service.create_profile("חג")
        impact = await service.delete_impact(target.id)
        assert impact == {"weeks": 0, "assignments": 0, "is_last": False}

    async def test_impact_flags_last_profile(self, service):
        only = await service.create_profile("שגרה")
        impact = await service.delete_impact(only.id)
        assert impact["is_last"] is True

    async def test_impact_unknown_profile_raises(self, service):
        import uuid

        with pytest.raises(ProfileNotFoundException):
            await service.delete_impact(uuid.uuid4())


class TestSeed:
    async def test_seed_creates_default_once(self, service):
        await service.seed_default_profile()
        profiles = await service.list_profiles()
        assert len(profiles) == 1
        assert profiles[0].name == DEFAULT_PROFILE_NAME
        assert profiles[0].is_default is True
        # The seeded profile is the permanent base template.
        assert profiles[0].is_base is True

    async def test_seed_idempotent(self, service):
        await service.seed_default_profile()
        await service.seed_default_profile()
        profiles = await service.list_profiles()
        assert len(profiles) == 1
