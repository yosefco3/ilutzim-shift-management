"""
Tests for AssignmentService (part B — schedule builder, task 05).
"""

from datetime import date
from unittest.mock import patch

import pytest

from app.constants import WeekStatus
from app.exceptions import (
    AssignmentNotFoundException,
    CellFullException,
    CellInactiveException,
    GuardAlreadyAssignedException,
    PositionNotFoundException,
    WeekNotEditableException,
    WeekNotFoundException,
)
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.services.assignment_service import AssignmentService


def _service(session):
    return AssignmentService(
        AssignmentRepository(session),
        ScheduleWeekRepository(session),
        PositionRepository(session),
    )


# Far-future default so the board-edit gate (start_date <= today → frozen) never
# trips for the generic assign/update/delete tests regardless of when they run.
async def _make_week(db_session, start=date(2099, 1, 5), status=WeekStatus.OPEN):
    week = ScheduleWeek(
        start_date=start,
        end_date=date(start.year, start.month, start.day + 6),
        status=status,
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _make_position(db_session, active_days=("0",), is_event=False,
                         event_required_count=None):
    profile = ActivationProfile(name="שגרה")
    db_session.add(profile)
    await db_session.flush()
    pos = Position(
        profile_id=profile.id,
        name="ארנונה",
        day_schedules={d: {"start": "07:00", "end": "15:00"} for d in active_days},
        is_event=is_event,
        event_required_count=event_required_count,
    )
    db_session.add(pos)
    await db_session.flush()
    return pos


async def _make_user(db_session, phone, roles=None, is_active=True):
    user = User(
        phone_number=phone, first_name="נתן", last_name="כהן",
        roles=roles or [], is_active=is_active,
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestAssignmentService:
    async def test_assign_persists(self, db_session):
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)

        a = await svc.assign(week.id, pos.id, 0, user.id)
        assert a.user_id == user.id
        rows = await svc.list_for_week(week.id)
        assert len(rows) == 1

    async def test_assign_with_segment(self, db_session):
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)

        a = await svc.assign(week.id, pos.id, 0, user.id, "19:00", "01:00")
        assert (a.segment_start, a.segment_end) == ("19:00", "01:00")

    async def test_assign_unknown_week(self, db_session):
        import uuid
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        with pytest.raises(WeekNotFoundException):
            await _service(db_session).assign(uuid.uuid4(), pos.id, 0, user.id)

    async def test_assign_unknown_position(self, db_session):
        import uuid
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111")
        with pytest.raises(PositionNotFoundException):
            await _service(db_session).assign(week.id, uuid.uuid4(), 0, user.id)

    async def test_assign_inactive_day_rejected(self, db_session):
        week = await _make_week(db_session)
        pos = await _make_position(db_session, active_days=("0",))
        user = await _make_user(db_session, "0501111111")
        with pytest.raises(CellInactiveException):
            await _service(db_session).assign(week.id, pos.id, 3, user.id)

    async def test_assign_missing_attribute_allowed(self, db_session):
        """A guard lacking a position's required attribute is still assignable."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        pos.required_attributes = ["armed"]
        await db_session.flush()
        user = await _make_user(db_session, "0501111111", roles=[])  # not armed
        a = await _service(db_session).assign(week.id, pos.id, 0, user.id)
        assert a.id is not None

    async def test_same_guard_twice_conflict(self, db_session):
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        await svc.assign(week.id, pos.id, 0, user.id)
        with pytest.raises(GuardAlreadyAssignedException):
            await svc.assign(week.id, pos.id, 0, user.id)

    async def test_second_guard_in_cell_allowed(self, db_session):
        """A different second guard in the same cell is allowed (tiling)."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        a_user = await _make_user(db_session, "0501111111")
        b_user = await _make_user(db_session, "0502222222")
        svc = _service(db_session)
        await svc.assign(week.id, pos.id, 0, a_user.id)
        b = await svc.assign(week.id, pos.id, 0, b_user.id)
        assert b.user_id == b_user.id
        assert len(await svc.list_for_week(week.id)) == 2

    async def test_third_guard_in_cell_blocked(self, db_session):
        """A third guard in the same cell is blocked (hard cap of two)."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        a_user = await _make_user(db_session, "0501111111")
        b_user = await _make_user(db_session, "0502222222")
        c_user = await _make_user(db_session, "0503333333")
        svc = _service(db_session)
        await svc.assign(week.id, pos.id, 0, a_user.id)
        await svc.assign(week.id, pos.id, 0, b_user.id)
        with pytest.raises(CellFullException):
            await svc.assign(week.id, pos.id, 0, c_user.id)

    async def test_event_position_exempt_from_cap(self, db_session):
        """An event (non-splitting) position holds any number of guards."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session, is_event=True)
        svc = _service(db_session)
        for i in range(4):
            user = await _make_user(db_session, f"05010000{i:02d}")
            a = await svc.assign(week.id, pos.id, 0, user.id)
            # Event placements never carry a time segment (whole window).
            assert a.segment_start is None and a.segment_end is None

    async def test_fixed_count_event_caps_at_required_count(self, db_session):
        """An event with a fixed participant count caps the cell at that many."""
        week = await _make_week(db_session)
        pos = await _make_position(db_session, is_event=True, event_required_count=3)
        svc = _service(db_session)
        for i in range(3):
            user = await _make_user(db_session, f"05010000{i:02d}")
            await svc.assign(week.id, pos.id, 0, user.id)
        # The 4th guard exceeds the fixed count of 3 → blocked.
        extra = await _make_user(db_session, "0509999999")
        with pytest.raises(CellFullException):
            await svc.assign(week.id, pos.id, 0, extra.id)

    async def test_update_segment_sets_window(self, db_session):
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        a = await svc.assign(week.id, pos.id, 0, user.id)
        updated = await svc.update_segment(a.id, "07:00", "14:00")
        assert (updated.segment_start, updated.segment_end) == ("07:00", "14:00")

    async def test_update_segment_back_to_null(self, db_session):
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        a = await svc.assign(week.id, pos.id, 0, user.id, "07:00", "14:00")
        updated = await svc.update_segment(a.id, None, None)
        assert (updated.segment_start, updated.segment_end) == (None, None)

    async def test_update_segment_unknown_id(self, db_session):
        import uuid
        with pytest.raises(AssignmentNotFoundException):
            await _service(db_session).update_segment(uuid.uuid4(), "07:00", "14:00")

    async def test_unassign(self, db_session):
        week = await _make_week(db_session)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        a = await svc.assign(week.id, pos.id, 0, user.id)

        assert await svc.unassign(a.id) is True
        assert await svc.list_for_week(week.id) == []

    async def test_unassign_missing_returns_false(self, db_session):
        import uuid
        assert await _service(db_session).unassign(uuid.uuid4()) is False


_GATE = "app.schedule_builder.services.assignment_service.today_il"


class TestBoardEditFreezesOnceStarted:
    """The board is editable only while the week is upcoming. Once it has started
    (start_date <= today — the Sunday rollover) it freezes, whatever the status.
    A future published (LOCKED) week is still editable and re-publishable."""

    async def test_assign_on_started_week_rejected(self, db_session):
        # Week starts 2026-07-05; "today" is 2026-07-10 → already started → frozen.
        week = await _make_week(db_session, start=date(2026, 7, 5),
                                status=WeekStatus.LOCKED)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        with patch(_GATE, return_value=date(2026, 7, 10)):
            with pytest.raises(WeekNotEditableException):
                await svc.assign(week.id, pos.id, 0, user.id)

    async def test_assign_on_started_open_week_rejected(self, db_session):
        # Same freeze applies even if the started week is somehow still OPEN.
        week = await _make_week(db_session, start=date(2026, 7, 5),
                                status=WeekStatus.OPEN)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        with patch(_GATE, return_value=date(2026, 7, 10)):
            with pytest.raises(WeekNotEditableException):
                await svc.assign(week.id, pos.id, 0, user.id)

    async def test_assign_on_published_upcoming_week_ok(self, db_session):
        # LOCKED (published) but still upcoming → editable / re-publishable.
        week = await _make_week(db_session, start=date(2026, 7, 12),
                                status=WeekStatus.LOCKED)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        with patch(_GATE, return_value=date(2026, 7, 10)):
            a = await svc.assign(week.id, pos.id, 0, user.id)
        assert a.user_id == user.id

    async def test_assign_on_upcoming_closed_week_ok(self, db_session):
        week = await _make_week(db_session, start=date(2026, 7, 12),
                                status=WeekStatus.CLOSED)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        with patch(_GATE, return_value=date(2026, 7, 10)):
            a = await svc.assign(week.id, pos.id, 0, user.id)
        assert a.user_id == user.id

    async def test_update_and_delete_respect_editability(self, db_session):
        # Build the assignment while the week is still upcoming (allowed)…
        week = await _make_week(db_session, start=date(2026, 7, 12),
                                status=WeekStatus.CLOSED)
        pos = await _make_position(db_session)
        user = await _make_user(db_session, "0501111111")
        svc = _service(db_session)
        with patch(_GATE, return_value=date(2026, 7, 10)):
            a = await svc.assign(week.id, pos.id, 0, user.id)
            # …still upcoming → update + (re)assign flow works.
            updated = await svc.update_segment(a.id, "07:00", "11:00")
            assert (updated.segment_start, updated.segment_end) == ("07:00", "11:00")

        # Now the week has started → both mutations are frozen.
        with patch(_GATE, return_value=date(2026, 7, 12)):
            with pytest.raises(WeekNotEditableException):
                await svc.update_segment(a.id, "07:00", "15:00")
            with pytest.raises(WeekNotEditableException):
                await svc.unassign(a.id)
