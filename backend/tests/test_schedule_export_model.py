"""
Tests for ScheduleExportService — the schedule read model (part B, task 10·01).

The read model is the single source of truth for who is placed on what and when.
Two cuts (``by_position`` / ``by_guard``) are exercised here, plus the pure
contiguous-merge helper that both cuts run through.

Note on the merge tests: the ``uq_assignment_cell_user`` constraint forbids the
*same* guard being placed twice on one position/day, so two back-to-back segments
for one guard on one position cannot exist as two DB rows. The merge is therefore
verified directly against ``_merge_contiguous`` (a pure function), while the "stays
split" guarantees (tiling between guards, two distinct positions) are verified
end-to-end through the DB.
"""

import uuid
from datetime import date

import pytest

from app.constants import WeekStatus
from app.exceptions import WeekNotFoundException
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.repositories.week_profile_repository import (
    WeekProfileRepository,
)
from app.schedule_builder.services.assignment_service import AssignmentService
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.services.schedule_export_service import (
    ScheduleExportService,
    _join_positions,
    _merge_contiguous,
)
from app.schedule_builder.services.week_profile_service import WeekProfileService


# The board-edit gate freezes assignments once a week has started; these fixtures
# use a 2026-07-05 week, so pin "today" before it stays editable regardless of the
# real clock (would otherwise trip after 2026-07-05).
@pytest.fixture(autouse=True)
def _pin_board_edit_clock():
    from unittest.mock import patch
    from datetime import date as _date
    with patch(
        "app.schedule_builder.services.assignment_service.today_il",
        return_value=_date(2026, 7, 1),
    ):
        yield


# ── fixtures / helpers ────────────────────────────────────────────────


def _board_service(session) -> BoardService:
    return BoardService(
        ScheduleWeekRepository(session),
        WeekProfileService(
            WeekProfileRepository(session),
            ProfileRepository(session),
            ScheduleWeekRepository(session),
        ),
        PositionRepository(session),
    )


def _assignment_service(session) -> AssignmentService:
    return AssignmentService(
        AssignmentRepository(session),
        ScheduleWeekRepository(session),
        PositionRepository(session),
    )


def _service(session) -> ScheduleExportService:
    return ScheduleExportService(
        _board_service(session),
        _assignment_service(session),
        UserRepository(session),
    )


async def _make_week(db_session, start=date(2026, 7, 5)):
    week = ScheduleWeek(
        start_date=start, end_date=date(2026, 7, 11), status=WeekStatus.OPEN
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _make_profile(db_session, name="שגרה", is_default=True):
    profile = ActivationProfile(name=name, is_default=is_default)
    db_session.add(profile)
    await db_session.flush()
    return profile


async def _add_position(db_session, profile, name="ארנונה", day_schedules=None):
    if day_schedules is None:
        day_schedules = {"0": {"start": "07:00", "end": "15:00"}}
    pos = Position(profile_id=profile.id, name=name, day_schedules=day_schedules)
    db_session.add(pos)
    await db_session.flush()
    return pos


async def _make_user(db_session, phone="0501111111", first="ישראל", last="ישראלי",
                     telegram_id=None):
    user = User(
        phone_number=phone, first_name=first, last_name=last,
        roles=[], is_active=True, telegram_id=telegram_id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _row_by_name(ws, name):
    return next(r for r in ws.by_position if r.name == name)


def _guard_by_id(ws, user_id):
    return next(g for g in ws.by_guard if g.user_id == user_id)


# ── tests ─────────────────────────────────────────────────────────────


class TestByPosition:
    async def test_single_assignment_takes_day_window(self, db_session):
        profile = await _make_profile(db_session)
        pos = await _add_position(db_session, profile, name="ארנונה")
        week = await _make_week(db_session)
        user = await _make_user(db_session, first="ישראל", last="ישראלי")
        await _assignment_service(db_session).assign(week.id, pos.id, 0, user.id)

        ws = await _service(db_session).get_week_schedule(week.id)

        row = _row_by_name(ws, "ארנונה")
        placements = row.days[0].placements
        assert len(placements) == 1
        assert placements[0].user_name == "ישראל ישראלי"
        assert (placements[0].start, placements[0].end) == ("07:00", "15:00")

    async def test_tiled_cell_keeps_two_placements_with_segments(self, db_session):
        profile = await _make_profile(db_session)
        pos = await _add_position(
            db_session, profile,
            day_schedules={"0": {"start": "07:00", "end": "19:00"}},
        )
        week = await _make_week(db_session)
        u1 = await _make_user(db_session, "0501111111", "אבי", "כהן")
        u2 = await _make_user(db_session, "0502222222", "דנה", "לוי")
        asvc = _assignment_service(db_session)
        await asvc.assign(week.id, pos.id, 0, u1.id, "07:00", "13:00")
        await asvc.assign(week.id, pos.id, 0, u2.id, "13:00", "19:00")

        ws = await _service(db_session).get_week_schedule(week.id)
        placements = _row_by_name(ws, "ארנונה").days[0].placements

        # Tiling between distinct guards stays split, ordered by start.
        assert [(p.user_name, p.start, p.end) for p in placements] == [
            ("אבי כהן", "07:00", "13:00"),
            ("דנה לוי", "13:00", "19:00"),
        ]

    async def test_partial_coverage_exposes_gap(self, db_session):
        # One guard covers 08:00–15:00 of a 07:00–15:00 window → the 07:00–08:00
        # start is an uncovered gap the exporter renders as an amber sub-row.
        profile = await _make_profile(db_session)
        pos = await _add_position(db_session, profile, name="ארנונה")
        week = await _make_week(db_session)
        user = await _make_user(db_session, first="ישראל", last="ישראלי")
        await _assignment_service(db_session).assign(
            week.id, pos.id, 0, user.id, "08:00", "15:00"
        )

        ws = await _service(db_session).get_week_schedule(week.id)
        day0 = _row_by_name(ws, "ארנונה").days[0]

        assert [(p.start, p.end) for p in day0.placements] == [("08:00", "15:00")]
        assert day0.gaps == [("07:00", "08:00")]

    async def test_fully_covered_cell_has_no_gap(self, db_session):
        profile = await _make_profile(db_session)
        pos = await _add_position(db_session, profile, name="ארנונה")
        week = await _make_week(db_session)
        user = await _make_user(db_session, first="ישראל", last="ישראלי")
        await _assignment_service(db_session).assign(week.id, pos.id, 0, user.id)

        ws = await _service(db_session).get_week_schedule(week.id)
        assert _row_by_name(ws, "ארנונה").days[0].gaps == []

    async def test_override_day_uses_that_days_window(self, db_session):
        # Day 0 canonical 07:00–15:00, day 1 overridden to 09:00–17:00.
        profile = await _make_profile(db_session)
        pos = await _add_position(
            db_session, profile,
            day_schedules={
                "0": {"start": "07:00", "end": "15:00"},
                "1": {"start": "09:00", "end": "17:00"},
            },
        )
        week = await _make_week(db_session)
        user = await _make_user(db_session)
        await _assignment_service(db_session).assign(week.id, pos.id, 1, user.id)

        ws = await _service(db_session).get_week_schedule(week.id)
        day1 = _row_by_name(ws, "ארנונה").days[1]
        assert (day1.placements[0].start, day1.placements[0].end) == ("09:00", "17:00")

    async def test_cross_midnight_hours_kept_as_is(self, db_session):
        profile = await _make_profile(db_session)
        pos = await _add_position(
            db_session, profile, name="סייר",
            day_schedules={"4": {"start": "23:00", "end": "07:00"}},
        )
        week = await _make_week(db_session)
        user = await _make_user(db_session)
        await _assignment_service(db_session).assign(week.id, pos.id, 4, user.id)

        ws = await _service(db_session).get_week_schedule(week.id)
        p = _row_by_name(ws, "סייר").days[4].placements[0]
        assert (p.start, p.end) == ("23:00", "07:00")

    async def test_inactive_day_has_no_placements(self, db_session):
        profile = await _make_profile(db_session)
        pos = await _add_position(db_session, profile)  # active only on day 0
        week = await _make_week(db_session)

        ws = await _service(db_session).get_week_schedule(week.id)
        row = _row_by_name(ws, "ארנונה")
        assert row.days[3].active is False
        assert row.days[3].placements == []


class TestByGuard:
    async def test_guard_with_shifts_sorted_and_empty_guard_present(self, db_session):
        profile = await _make_profile(db_session)
        pos = await _add_position(
            db_session, profile, name="ארנונה",
            day_schedules={str(d): {"start": "07:00", "end": "15:00"} for d in range(7)},
        )
        week = await _make_week(db_session)
        worker = await _make_user(db_session, "0501111111", "אבי", "כהן")
        idle = await _make_user(db_session, "0502222222", "דנה", "לוי")
        asvc = _assignment_service(db_session)
        # Assign out of order to prove sorting.
        await asvc.assign(week.id, pos.id, 3, worker.id)
        await asvc.assign(week.id, pos.id, 0, worker.id)
        await asvc.assign(week.id, pos.id, 5, worker.id)

        ws = await _service(db_session).get_week_schedule(week.id)

        w = _guard_by_id(ws, worker.id)
        assert [s.day_index for s in w.shifts] == [0, 3, 5]
        assert all(s.position_name == "ארנונה" for s in w.shifts)
        assert w.shifts[0].date == "2026-07-05"

        i = _guard_by_id(ws, idle.id)
        assert i.shifts == []

    async def test_two_positions_same_day_merge_with_joined_names(self, db_session):
        # Contiguous hours across *different* positions merge into one span for the
        # per-guard cut, joining the position names (07–15 + 15–19 → 07–19).
        profile = await _make_profile(db_session)
        p1 = await _add_position(
            db_session, profile, name="ארנונה",
            day_schedules={"0": {"start": "07:00", "end": "15:00"}},
        )
        p2 = await _add_position(
            db_session, profile, name="קומה 6",
            day_schedules={"0": {"start": "15:00", "end": "19:00"}},
        )
        week = await _make_week(db_session)
        user = await _make_user(db_session)
        asvc = _assignment_service(db_session)
        await asvc.assign(week.id, p1.id, 0, user.id)
        await asvc.assign(week.id, p2.id, 0, user.id)

        ws = await _service(db_session).get_week_schedule(week.id)
        shifts = _guard_by_id(ws, user.id).shifts
        assert [(s.position_name, s.start, s.end) for s in shifts] == [
            ("ארנונה / קומה 6", "07:00", "19:00"),
        ]

    async def test_two_positions_same_day_with_gap_stay_split(self, db_session):
        # A gap between the two positions' hours is a genuine break — no merge.
        profile = await _make_profile(db_session)
        p1 = await _add_position(
            db_session, profile, name="ארנונה",
            day_schedules={"0": {"start": "07:00", "end": "11:00"}},
        )
        p2 = await _add_position(
            db_session, profile, name="קומה 6",
            day_schedules={"0": {"start": "15:00", "end": "19:00"}},
        )
        week = await _make_week(db_session)
        user = await _make_user(db_session)
        asvc = _assignment_service(db_session)
        await asvc.assign(week.id, p1.id, 0, user.id)
        await asvc.assign(week.id, p2.id, 0, user.id)

        ws = await _service(db_session).get_week_schedule(week.id)
        shifts = _guard_by_id(ws, user.id).shifts
        assert [(s.position_name, s.start, s.end) for s in shifts] == [
            ("ארנונה", "07:00", "11:00"),
            ("קומה 6", "15:00", "19:00"),
        ]

    async def test_telegram_id_surfaced(self, db_session):
        await _make_profile(db_session)
        week = await _make_week(db_session)
        user = await _make_user(db_session, telegram_id="123456")

        ws = await _service(db_session).get_week_schedule(week.id)
        assert _guard_by_id(ws, user.id).telegram_id == "123456"


class TestUnknownWeek:
    async def test_unknown_week_raises(self, db_session):
        with pytest.raises(WeekNotFoundException):
            await _service(db_session).get_week_schedule(uuid.uuid4())


class TestMergeContiguous:
    """The merge is a pure function; the DB can't produce same-guard/same-cell
    duplicates, so contiguity is verified here directly."""

    def test_by_position_key_merges_same_guard_runs(self):
        uid = uuid.uuid4()
        shifts = [
            {"user_id": uid, "user_name": "אבי", "start": "07:00", "end": "15:00"},
            {"user_id": uid, "user_name": "אבי", "start": "15:00", "end": "19:00"},
        ]
        merged = _merge_contiguous(shifts, key=lambda s: s["user_id"])
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == ("07:00", "19:00")

    def test_chains_three_segments(self):
        uid = uuid.uuid4()
        shifts = [
            {"user_id": uid, "start": "15:00", "end": "19:00"},
            {"user_id": uid, "start": "07:00", "end": "15:00"},
            {"user_id": uid, "start": "19:00", "end": "23:00"},
        ]
        merged = _merge_contiguous(shifts, key=lambda s: s["user_id"])
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == ("07:00", "23:00")

    def test_by_guard_key_merges_same_position_run(self):
        pid = uuid.uuid4()
        shifts = [
            {"day_index": 0, "position_id": pid, "start": "07:00", "end": "15:00"},
            {"day_index": 0, "position_id": pid, "start": "15:00", "end": "19:00"},
        ]
        merged = _merge_contiguous(
            shifts, key=lambda s: (s["day_index"], s["position_id"])
        )
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == ("07:00", "19:00")

    def test_by_guard_key_merges_across_positions_joining_names(self):
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        shifts = [
            {"day_index": 0, "position_id": p1, "position_name": "אחראי משמרת",
             "start": "07:00", "end": "15:00"},
            {"day_index": 0, "position_id": p2, "position_name": "אחראי משמרת (ערב)",
             "start": "15:00", "end": "19:00"},
        ]
        merged = _merge_contiguous(
            shifts, key=lambda s: s["day_index"], combine=_join_positions
        )
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == ("07:00", "19:00")
        assert merged[0]["position_name"] == "אחראי משמרת / אחראי משמרת (ערב)"
        # Keeps the first placement's position_id for identity.
        assert merged[0]["position_id"] == p1

    def test_join_positions_does_not_duplicate_repeated_name(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        shifts = [
            {"day_index": 0, "position_id": a, "position_name": "A",
             "start": "07:00", "end": "11:00"},
            {"day_index": 0, "position_id": b, "position_name": "B",
             "start": "11:00", "end": "15:00"},
            {"day_index": 0, "position_id": a, "position_name": "A",
             "start": "15:00", "end": "19:00"},
        ]
        merged = _merge_contiguous(
            shifts, key=lambda s: s["day_index"], combine=_join_positions
        )
        assert len(merged) == 1
        assert merged[0]["position_name"] == "A / B"
        assert (merged[0]["start"], merged[0]["end"]) == ("07:00", "19:00")

    def test_distinct_keys_stay_split(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        shifts = [
            {"user_id": a, "start": "07:00", "end": "15:00"},
            {"user_id": b, "start": "15:00", "end": "19:00"},
        ]
        merged = _merge_contiguous(shifts, key=lambda s: s["user_id"])
        assert len(merged) == 2

    def test_non_contiguous_stays_split(self):
        uid = uuid.uuid4()
        shifts = [
            {"user_id": uid, "start": "07:00", "end": "11:00"},
            {"user_id": uid, "start": "15:00", "end": "19:00"},
        ]
        merged = _merge_contiguous(shifts, key=lambda s: s["user_id"])
        assert len(merged) == 2

    def test_overlap_widens_and_does_not_crash(self):
        uid = uuid.uuid4()
        shifts = [
            {"user_id": uid, "start": "07:00", "end": "16:00"},
            {"user_id": uid, "start": "15:00", "end": "19:00"},
        ]
        merged = _merge_contiguous(shifts, key=lambda s: s["user_id"])
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == ("07:00", "19:00")

    def test_merges_night_tail_into_morning(self):
        # A night tail ending at the 07:00 anchor + a morning span starting at it
        # are one continuous presence on the 07:00→07:00 axis, not two reversed
        # segments (the B-2 bug: wall-clock sort put 01:00 before 07:00 and split).
        uid = uuid.uuid4()
        shifts = [
            {"user_id": uid, "start": "07:00", "end": "15:00"},
            {"user_id": uid, "start": "01:00", "end": "07:00"},
        ]
        merged = _merge_contiguous(shifts, key=lambda s: s["user_id"])
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == ("01:00", "15:00")

    def test_wrap_segment_orders_after_evening(self):
        # 23:00–01:00 (crosses midnight) + 01:00–07:00 (night tail) chain on the
        # anchor axis into one 23:00–07:00 span, not displayed reversed.
        uid = uuid.uuid4()
        shifts = [
            {"user_id": uid, "start": "01:00", "end": "07:00"},
            {"user_id": uid, "start": "23:00", "end": "01:00"},
        ]
        merged = _merge_contiguous(shifts, key=lambda s: s["user_id"])
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == ("23:00", "07:00")
