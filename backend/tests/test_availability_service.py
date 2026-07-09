"""
Tests for AvailabilityService (part B — schedule builder, task 06).

Covers the enriched pool: per-day availability, the union rule for hours,
assigned/remaining hours, sorting by remaining, and notes.
"""

from datetime import date, time

import pytest

from app.constants import ShiftType, WeekStatus
from app.exceptions import WeekNotFoundException
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.models.weekly_submission import WeeklySubmission
from app.models.daily_status import DailyStatus
from app.models.shift_window import ShiftWindow
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.services.availability_service import (
    AvailabilityService,
    _clamp_to_anchor,
)


def _service(session):
    return AvailabilityService(
        ScheduleWeekRepository(session),
        SubmissionRepository(session),
        UserRepository(session),
        AssignmentRepository(session),
        PositionRepository(session),
    )


async def _make_week(db_session, start=date(2026, 7, 5)):
    week = ScheduleWeek(
        start_date=start, end_date=date(2026, 7, 11), status=WeekStatus.OPEN
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _make_user(db_session, phone, first="נתן", roles=None, is_active=True):
    user = User(
        phone_number=phone, first_name=first, last_name="כהן",
        roles=roles or [], is_active=is_active,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _submit(db_session, user, week, day_windows, notes=None):
    """day_windows: {day_index: [(start_time, end_time), …]} as 'HH:MM' strings."""
    sub = WeeklySubmission(user_id=user.id, week_id=week.id, general_notes=notes)
    db_session.add(sub)
    await db_session.flush()
    for day_index, windows in day_windows.items():
        ds = DailyStatus(
            submission_id=sub.id,
            date=date(2026, 7, 5 + day_index),
            is_available=True,
        )
        db_session.add(ds)
        await db_session.flush()
        for s, e in windows:
            sh, sm = map(int, s.split(":"))
            eh, em = map(int, e.split(":"))
            db_session.add(ShiftWindow(
                daily_status_id=ds.id, shift_type=ShiftType.MORNING,
                start_time=time(sh, sm), end_time=time(eh, em),
            ))
    await db_session.flush()
    return sub


async def _make_position(db_session, day_schedules):
    profile = ActivationProfile(name="שגרה")
    db_session.add(profile)
    await db_session.flush()
    pos = Position(profile_id=profile.id, name="ארנונה", day_schedules=day_schedules)
    db_session.add(pos)
    await db_session.flush()
    return pos


class TestAvailabilityService:
    async def test_union_rule_for_hours(self, db_session):
        """Overlapping windows on a day count as their union, not their sum."""
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111")
        # 07:00–16:30 ∪ 15:00–19:00 = 12h (not 13.5h).
        await _submit(db_session, user, week, {0: [("07:00", "16:30"), ("15:00", "19:00")]})

        pool = await _service(db_session).build_pool(week.id)
        assert len(pool) == 1
        assert pool[0]["available_hours"] == 12.0
        # The merged window is exposed for colouring.
        assert pool[0]["availability"]["0"] == [{"start": "07:00", "end": "19:00"}]

    async def test_notes_and_roles_surfaced(self, db_session):
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111", roles=["armed"])
        await _submit(db_session, user, week, {0: [("07:00", "15:00")]}, notes="עדיפות לבקרים")

        guard = (await _service(db_session).build_pool(week.id))[0]
        assert guard["notes"] == "עדיפות לבקרים"
        assert guard["roles"] == ["armed"]

    async def test_night_window_hours(self, db_session):
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111")
        await _submit(db_session, user, week, {2: [("19:00", "07:00")]})
        guard = (await _service(db_session).build_pool(week.id))[0]
        assert guard["available_hours"] == 12.0

    async def test_early_morning_start_does_not_bleed_into_night(self, db_session):
        """A 06:30 morning start is clamped to 07:00 — it must not wrap onto the
        night band and fake night availability (regression: 06:30 → phantom
        partial night coverage)."""
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111")
        await _submit(db_session, user, week, {0: [("06:30", "15:00")]})

        guard = (await _service(db_session).build_pool(week.id))[0]
        # No 06:30–07:00 sliver — the window starts at the anchor.
        assert guard["availability"]["0"] == [{"start": "07:00", "end": "15:00"}]
        assert guard["available_hours"] == 8.0  # 07:00–15:00, not 8.5h
        # Coverage against a night position is genuinely empty, not "partial".
        from app.schedule_builder.utils import intervals as iv
        windows = [(w["start"], w["end"]) for w in guard["availability"]["0"]]
        avail = iv.merge([p for s, e in windows for p in iv.normalize(s, e)])
        assert iv.coverage("23:00", "07:00", avail)["state"] == "none"

    async def test_window_entirely_before_anchor_is_dropped(self, db_session):
        """A window living wholly before 07:00 contributes nothing to the day."""
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111")
        await _submit(db_session, user, week, {0: [("05:00", "06:30")]})

        guard = (await _service(db_session).build_pool(week.id))[0]
        assert "0" not in guard["availability"]
        assert guard["available_hours"] == 0.0

    async def test_wrapping_window_before_anchor_is_clamped(self, db_session):
        """An import window that both starts before 07:00 and wraps midnight
        (05:00–02:00) must have its 05:00–07:00 sliver clamped away — no phantom
        availability lands in the night tail before the anchor."""
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111")
        await _submit(db_session, user, week, {0: [("05:00", "02:00")]})

        guard = (await _service(db_session).build_pool(week.id))[0]
        # Start clamped up to the anchor; the pre-07:00 sliver is gone.
        assert guard["availability"]["0"] == [{"start": "07:00", "end": "02:00"}]
        assert guard["available_hours"] == 19.0  # 07:00→02:00, not 21h with sliver
        # No availability fragment sits before 07:00 on the security-day axis.
        from app.schedule_builder.utils import intervals as iv
        windows = [(w["start"], w["end"]) for w in guard["availability"]["0"]]
        avail = iv.merge([p for s, e in windows for p in iv.normalize(s, e)])
        # The pre-anchor sliver (05:00–07:00) is uncovered — clamped away.
        assert iv.coverage("05:00", "07:00", avail)["state"] == "none"

    def test_genuine_night_windows_unchanged(self):
        """Night shifts starting at/after 07:00 are never touched by the clamp."""
        assert _clamp_to_anchor(time(19, 0), time(7, 0)) == ("19:00", "07:00")
        assert _clamp_to_anchor(time(23, 0), time(7, 0)) == ("23:00", "07:00")

    async def test_assigned_reduces_remaining(self, db_session):
        """Assigning the guard to a cell consumes that window from remaining."""
        week = await _make_week(db_session)
        user = await _make_user(db_session, "0501111111")
        await _submit(db_session, user, week, {0: [("07:00", "19:00")]})  # 12h
        pos = await _make_position(db_session, {"0": {"start": "07:00", "end": "15:00"}})
        db_session.add(ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=0, user_id=user.id
        ))
        await db_session.flush()

        guard = (await _service(db_session).build_pool(week.id))[0]
        assert guard["available_hours"] == 12.0
        assert guard["assigned_hours"] == 8.0  # 07:00–15:00
        assert guard["remaining_hours"] == 4.0

    async def test_sorted_by_remaining_desc(self, db_session):
        week = await _make_week(db_session)
        busy = await _make_user(db_session, "0501111111", first="בזי")
        free = await _make_user(db_session, "0502222222", first="פנוי")
        await _submit(db_session, busy, week, {0: [("07:00", "11:00")]})   # 4h
        await _submit(db_session, free, week, {0: [("07:00", "19:00")]})   # 12h

        pool = await _service(db_session).build_pool(week.id)
        assert [g["full_name"].split()[0] for g in pool] == ["פנוי", "בזי"]

    async def test_excludes_inactive(self, db_session):
        week = await _make_week(db_session)
        active = await _make_user(db_session, "0501111111")
        inactive = await _make_user(db_session, "0502222222", is_active=False)
        await _submit(db_session, active, week, {0: [("07:00", "15:00")]})
        await _submit(db_session, inactive, week, {0: [("07:00", "15:00")]})
        # An inactive user who never submitted is excluded from the
        # unsubmitted tail too.
        await _make_user(db_session, "0503333333", is_active=False)

        pool = await _service(db_session).build_pool(week.id)
        assert [g["id"] for g in pool] == [active.id]

    async def test_unknown_week_raises(self, db_session):
        import uuid
        with pytest.raises(WeekNotFoundException):
            await _service(db_session).build_pool(uuid.uuid4())


class _StubSettings:
    """Settings stand-in — returns a fixed pool_show_unsubmitted value."""

    def __init__(self, value):
        self._value = value

    async def get_setting(self, key):
        assert key == "pool_show_unsubmitted"
        return self._value


def _service_with_setting(session, value):
    return AvailabilityService(
        ScheduleWeekRepository(session),
        SubmissionRepository(session),
        UserRepository(session),
        AssignmentRepository(session),
        PositionRepository(session),
        settings_service=_StubSettings(value),
    )


class TestUnsubmittedInPool:
    """pool_show_unsubmitted — active non-submitters at the end of the pool."""

    async def test_unsubmitted_appended_last_by_name(self, db_session):
        week = await _make_week(db_session)
        submitted = await _make_user(db_session, "0501111111", first="זריז")
        await _submit(db_session, submitted, week, {0: [("07:00", "11:00")]})
        late_b = await _make_user(db_session, "0502222222", first="בני")
        late_a = await _make_user(db_session, "0503333333", first="אבי")

        pool = await _service(db_session).build_pool(week.id)  # default ON
        assert [g["id"] for g in pool] == [submitted.id, late_a.id, late_b.id]
        tail = pool[1]
        assert tail["submitted"] is False
        assert tail["availability"] == {}
        assert tail["available_hours"] == 0.0
        assert tail["notes"] is None
        assert pool[0]["submitted"] is True

    async def test_unsubmitted_after_used_up_submitters(self, db_session):
        """Even a fully-consumed submitter sorts before a non-submitter."""
        week = await _make_week(db_session)
        used_up = await _make_user(db_session, "0501111111", first="עסוק")
        await _submit(db_session, used_up, week, {0: [("07:00", "15:00")]})  # 8h
        pos = await _make_position(db_session, {"0": {"start": "07:00", "end": "15:00"}})
        db_session.add(ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=0, user_id=used_up.id
        ))
        await db_session.flush()
        late = await _make_user(db_session, "0502222222", first="אבי")

        pool = await _service(db_session).build_pool(week.id)
        assert [g["id"] for g in pool] == [used_up.id, late.id]
        assert pool[0]["remaining_hours"] == 0.0

    async def test_setting_off_hides_unsubmitted(self, db_session):
        week = await _make_week(db_session)
        submitted = await _make_user(db_session, "0501111111")
        await _submit(db_session, submitted, week, {0: [("07:00", "15:00")]})
        late = await _make_user(db_session, "0502222222")

        service = _service_with_setting(db_session, "false")
        pool = await service.build_pool(week.id)
        assert [g["id"] for g in pool] == [submitted.id]
        # The warnings path forces them back in regardless of the setting.
        forced = await service.build_pool(week.id, include_unsubmitted=True)
        assert late.id in [g["id"] for g in forced]

    async def test_setting_on_string_true(self, db_session):
        week = await _make_week(db_session)
        late = await _make_user(db_session, "0502222222")
        pool = await _service_with_setting(db_session, "true").build_pool(week.id)
        assert [g["id"] for g in pool] == [late.id]

    async def test_hidden_unsubmitted_keeps_his_assignment(self, db_session):
        """Switch OFF removes the guard from the pool — never his assignments."""
        week = await _make_week(db_session)
        late = await _make_user(db_session, "0502222222")
        pos = await _make_position(db_session, {"0": {"start": "07:00", "end": "15:00"}})
        db_session.add(ScheduleAssignment(
            week_id=week.id, position_id=pos.id, day_index=0, user_id=late.id
        ))
        await db_session.flush()

        service = _service_with_setting(db_session, "false")
        assert await service.build_pool(week.id) == []
        # The assignment survives, and the warnings-path pool sees its hours.
        rows = await AssignmentRepository(db_session).list_for_week(week.id)
        assert [a.user_id for a in rows] == [late.id]
        forced = await service.build_pool(week.id, include_unsubmitted=True)
        assert forced[0]["assigned_hours"] == 8.0
        assert forced[0]["remaining_hours"] == -8.0
        assert forced[0]["submitted"] is False
