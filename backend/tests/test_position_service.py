"""
Tests for PositionService (part B — schedule builder).
"""

import uuid

import pytest

from app.exceptions import (
    PositionBulkMismatchException,
    PositionNotFoundException,
    PositionReorderMismatchException,
    ProfileNotFoundException,
)
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.services.position_service import PositionService


@pytest.fixture
def service(db_session):
    return PositionService(PositionRepository(db_session), ProfileRepository(db_session))


async def _make_profile(db_session, name="שגרה"):
    profile = ActivationProfile(name=name)
    db_session.add(profile)
    await db_session.flush()
    return profile


class TestCrud:
    async def test_create_then_list_ordered(self, service, db_session):
        profile = await _make_profile(db_session)
        await service.create_position(profile.id, "ארנונה")
        await service.create_position(profile.id, "קומה 6")
        positions = await service.list_positions(profile.id)

        assert [p.name for p in positions] == ["ארנונה", "קומה 6"]
        assert positions[0].display_order < positions[1].display_order

    async def test_display_order_is_per_profile(self, service, db_session):
        a = await _make_profile(db_session, "שגרה")
        b = await _make_profile(db_session, "חג")
        await service.create_position(a.id, "א1")
        first_b = await service.create_position(b.id, "ב1")
        # Profile b starts its own ordering at 1.
        assert first_b.display_order == 1

    async def test_create_with_payload(self, service, db_session):
        profile = await _make_profile(db_session)
        sched = {"0": {"start": "07:30", "end": "15:00"}}
        pos = await service.create_position(
            profile.id, "ארנונה",
            day_schedules=sched, required_attributes=["armed"],
        )
        assert pos.day_schedules == sched
        assert pos.required_attributes == ["armed"]

    async def test_is_event_defaults_false_and_round_trips(self, service, db_session):
        profile = await _make_profile(db_session)
        normal = await service.create_position(profile.id, "ארנונה")
        event = await service.create_position(
            profile.id, "רענון", is_event=True
        )
        assert normal.is_event is False
        assert event.is_event is True

    async def test_update_toggles_is_event(self, service, db_session):
        profile = await _make_profile(db_session)
        pos = await service.create_position(profile.id, "רענון", is_event=True)
        updated = await service.update_position(pos.id, is_event=False)
        assert updated.is_event is False
        # Updating only the name leaves is_event untouched.
        again = await service.update_position(pos.id, name="רענון נשק")
        assert again.is_event is False

    async def test_copy_preserves_is_event(self, service, db_session):
        a = await _make_profile(db_session, "שגרה")
        b = await _make_profile(db_session, "חג")
        src = await service.create_position(a.id, "רענון", is_event=True)
        copy = await service.copy_position(src.id, b.id)
        assert copy.is_event is True

    async def test_event_required_count_round_trips(self, service, db_session):
        profile = await _make_profile(db_session)
        pos = await service.create_position(
            profile.id, "מועצה", is_event=True, event_required_count=4
        )
        assert pos.event_required_count == 4

    async def test_required_count_forced_none_when_not_event(self, service, db_session):
        """The fixed count is event-only — a normal position never keeps one."""
        profile = await _make_profile(db_session)
        pos = await service.create_position(
            profile.id, "ארנונה", is_event=False, event_required_count=4
        )
        assert pos.event_required_count is None

    async def test_update_clears_count_when_event_turned_off(self, service, db_session):
        profile = await _make_profile(db_session)
        pos = await service.create_position(
            profile.id, "מועצה", is_event=True, event_required_count=4
        )
        updated = await service.update_position(pos.id, is_event=False)
        assert updated.is_event is False
        assert updated.event_required_count is None

    async def test_update_clears_count_to_unlimited_while_event(self, service, db_session):
        """Unchecking the fixed-count box (event stays on) → back to unlimited."""
        profile = await _make_profile(db_session)
        pos = await service.create_position(
            profile.id, "מועצה", is_event=True, event_required_count=4
        )
        updated = await service.update_position(
            pos.id, is_event=True, event_required_count=None
        )
        assert updated.is_event is True
        assert updated.event_required_count is None

    async def test_copy_preserves_event_required_count(self, service, db_session):
        a = await _make_profile(db_session, "שגרה")
        b = await _make_profile(db_session, "חג")
        src = await service.create_position(
            a.id, "מועצה", is_event=True, event_required_count=4
        )
        copy = await service.copy_position(src.id, b.id)
        assert copy.event_required_count == 4

    async def test_update_only_provided_fields(self, service, db_session):
        profile = await _make_profile(db_session)
        pos = await service.create_position(
            profile.id, "ארנונה",
            day_schedules={"0": {"start": "07:00", "end": "15:00"}},
            required_attributes=["armed"],
        )
        new_sched = {"1": {"start": "08:00", "end": "16:00"}}
        updated = await service.update_position(pos.id, day_schedules=new_sched)

        assert updated.day_schedules == new_sched
        assert updated.name == "ארנונה"  # untouched
        assert updated.required_attributes == ["armed"]  # untouched

    async def test_delete(self, service, db_session):
        profile = await _make_profile(db_session)
        pos = await service.create_position(profile.id, "ארנונה")
        await service.delete_position(pos.id)
        assert await service.list_positions(profile.id) == []

    async def test_get_missing_raises(self, service):
        with pytest.raises(PositionNotFoundException):
            await service.get_position(uuid.uuid4())

    async def test_delete_missing_raises(self, service):
        with pytest.raises(PositionNotFoundException):
            await service.delete_position(uuid.uuid4())


class TestReorder:
    async def test_reorder_rewrites_display_order(self, service, db_session):
        profile = await _make_profile(db_session)
        a = await service.create_position(profile.id, "א")
        b = await service.create_position(profile.id, "ב")
        c = await service.create_position(profile.id, "ג")

        reordered = await service.reorder_positions(profile.id, [c.id, a.id, b.id])

        assert [p.name for p in reordered] == ["ג", "א", "ב"]
        assert [p.display_order for p in reordered] == [0, 1, 2]
        # A fresh list reflects the new order too.
        names = [p.name for p in await service.list_positions(profile.id)]
        assert names == ["ג", "א", "ב"]

    async def test_reorder_missing_id_raises(self, service, db_session):
        profile = await _make_profile(db_session)
        a = await service.create_position(profile.id, "א")
        await service.create_position(profile.id, "ב")
        # Only one of the two positions -> not a full permutation.
        with pytest.raises(PositionReorderMismatchException):
            await service.reorder_positions(profile.id, [a.id])

    async def test_reorder_foreign_id_raises(self, service, db_session):
        profile = await _make_profile(db_session)
        a = await service.create_position(profile.id, "א")
        with pytest.raises(PositionReorderMismatchException):
            await service.reorder_positions(profile.id, [a.id, uuid.uuid4()])


class TestBulkDaySchedules:
    async def test_updates_subset_leaves_third_untouched(self, service, db_session):
        profile = await _make_profile(db_session)
        sched = {"0": {"start": "07:00", "end": "15:00"}}
        a = await service.create_position(profile.id, "א", day_schedules=sched)
        b = await service.create_position(profile.id, "ב", day_schedules=sched)
        c = await service.create_position(profile.id, "ג", day_schedules=sched)

        new_a = {"1": {"start": "08:00", "end": "16:00"}}
        new_b = {"2": {"start": "09:00", "end": "17:00"}}
        result = await service.bulk_update_day_schedules(
            profile.id, [(a.id, new_a), (b.id, new_b)]
        )

        # Full ordered list returned (same shape as list_positions).
        assert [p.name for p in result] == ["א", "ב", "ג"]
        by_id = {p.id: p for p in result}
        assert by_id[a.id].day_schedules == new_a
        assert by_id[b.id].day_schedules == new_b
        # The unmentioned position is untouched [EDGE C1].
        assert by_id[c.id].day_schedules == sched

    async def test_empty_schedules_closes_position(self, service, db_session):
        profile = await _make_profile(db_session)
        a = await service.create_position(
            profile.id, "א", day_schedules={"0": {"start": "07:00", "end": "15:00"}}
        )
        result = await service.bulk_update_day_schedules(profile.id, [(a.id, {})])
        assert result[0].day_schedules == {}  # [EDGE D3]

    async def test_overnight_window_allowed(self, service, db_session):
        profile = await _make_profile(db_session)
        a = await service.create_position(
            profile.id, "א", day_schedules={"0": {"start": "07:00", "end": "15:00"}}
        )
        night = {"0": {"start": "23:00", "end": "07:00"}}
        result = await service.bulk_update_day_schedules(profile.id, [(a.id, night)])
        assert result[0].day_schedules == night  # [EDGE D2]

    async def test_unknown_id_raises_and_writes_nothing(self, service, db_session):
        profile = await _make_profile(db_session)
        sched = {"0": {"start": "07:00", "end": "15:00"}}
        a = await service.create_position(profile.id, "א", day_schedules=sched)
        with pytest.raises(PositionBulkMismatchException):
            await service.bulk_update_day_schedules(
                profile.id,
                [(a.id, {"1": {"start": "08:00", "end": "16:00"}}),
                 (uuid.uuid4(), sched)],
            )
        # Nothing written — validation precedes any mutation [EDGE C2+N1].
        assert (await service.get_position(a.id)).day_schedules == sched

    async def test_other_profile_id_raises_and_writes_nothing(
        self, service, db_session
    ):
        profile = await _make_profile(db_session, "שגרה")
        other = await _make_profile(db_session, "אחר")
        sched = {"0": {"start": "07:00", "end": "15:00"}}
        a = await service.create_position(profile.id, "א", day_schedules=sched)
        foreign = await service.create_position(other.id, "זר", day_schedules=sched)
        with pytest.raises(PositionBulkMismatchException):
            await service.bulk_update_day_schedules(
                profile.id,
                [(a.id, {"1": {"start": "08:00", "end": "16:00"}}),
                 (foreign.id, sched)],
            )
        assert (await service.get_position(a.id)).day_schedules == sched

    async def test_duplicate_id_raises(self, service, db_session):
        profile = await _make_profile(db_session)
        a = await service.create_position(profile.id, "א")
        with pytest.raises(PositionBulkMismatchException):
            await service.bulk_update_day_schedules(
                profile.id,
                [(a.id, {"1": {"start": "08:00", "end": "16:00"}}),
                 (a.id, {"2": {"start": "09:00", "end": "17:00"}})],
            )

    async def test_message_carries_offending_ids(self, service, db_session):
        profile = await _make_profile(db_session)
        bad = uuid.uuid4()
        with pytest.raises(PositionBulkMismatchException) as exc_info:
            await service.bulk_update_day_schedules(profile.id, [(bad, {})])
        assert str(bad) in exc_info.value.message

    async def test_missing_profile_raises(self, service, db_session):
        with pytest.raises(ProfileNotFoundException):
            await service.bulk_update_day_schedules(uuid.uuid4(), [(uuid.uuid4(), {})])


class TestCopyToProfile:
    async def test_copy_creates_independent_deep_copy(self, service, db_session):
        src_profile = await _make_profile(db_session, "שגרה")
        dst_profile = await _make_profile(db_session, "חג")
        sched = {"0": {"start": "07:30", "end": "15:00"}}
        src = await service.create_position(
            src_profile.id, "ארנונה",
            day_schedules=sched, required_attributes=["armed"],
        )

        copy = await service.copy_position(src.id, dst_profile.id)

        assert copy.id != src.id
        assert copy.profile_id == dst_profile.id
        assert copy.name == "ארנונה"
        assert copy.day_schedules == sched
        assert copy.required_attributes == ["armed"]
        # The source profile keeps its single position; the target gains one.
        assert len(await service.list_positions(src_profile.id)) == 1
        assert len(await service.list_positions(dst_profile.id)) == 1

        # Deep copy: mutating the copy's JSON must not touch the source.
        copy.day_schedules["0"]["start"] = "09:00"
        copy.required_attributes.append("roni")
        fresh_src = await service.get_position(src.id)
        assert fresh_src.day_schedules == sched
        assert fresh_src.required_attributes == ["armed"]

    async def test_copy_appends_display_order_in_target(self, service, db_session):
        src_profile = await _make_profile(db_session, "שגרה")
        dst_profile = await _make_profile(db_session, "חג")
        await service.create_position(dst_profile.id, "קיים בחג")
        src = await service.create_position(src_profile.id, "ארנונה")

        copy = await service.copy_position(src.id, dst_profile.id)

        # Appended after the existing target position (order 1) -> order 2.
        assert copy.display_order == 2
        names = [p.name for p in await service.list_positions(dst_profile.id)]
        assert names == ["קיים בחג", "ארנונה"]

    async def test_copy_missing_source_raises(self, service, db_session):
        dst_profile = await _make_profile(db_session)
        with pytest.raises(PositionNotFoundException):
            await service.copy_position(uuid.uuid4(), dst_profile.id)

    async def test_copy_missing_target_profile_raises(self, service, db_session):
        src_profile = await _make_profile(db_session)
        src = await service.create_position(src_profile.id, "ארנונה")
        with pytest.raises(ProfileNotFoundException):
            await service.copy_position(src.id, uuid.uuid4())
