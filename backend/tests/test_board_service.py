"""
Tests for WeekProfileService + BoardService (part B — task 04 board skeleton).
"""

import uuid
from datetime import date

import pytest

from app.constants import WeekStatus
from app.exceptions import ProfileNotFoundException, WeekNotFoundException
from app.utils.date_utils import week_range
from app.models.schedule_week import ScheduleWeek
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.repositories.week_profile_repository import (
    WeekProfileRepository,
)
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.services.week_profile_service import WeekProfileService


# ── fixtures / helpers ────────────────────────────────────────────────

def _wp_service(session) -> WeekProfileService:
    return WeekProfileService(
        WeekProfileRepository(session),
        ProfileRepository(session),
        ScheduleWeekRepository(session),
    )


def _board_service(session) -> BoardService:
    return BoardService(
        ScheduleWeekRepository(session),
        _wp_service(session),
        PositionRepository(session),
    )


async def _make_week(db_session, start=date(2026, 7, 5)):
    week = ScheduleWeek(
        start_date=start, end_date=date(2026, 7, 11), status=WeekStatus.OPEN
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _make_profile(db_session, name="שגרה", is_default=False):
    profile = ActivationProfile(name=name, is_default=is_default)
    db_session.add(profile)
    await db_session.flush()
    return profile


async def _add_position(db_session, profile, name, day_schedules, order=0, requires=None, is_event=False):
    pos = Position(
        profile_id=profile.id,
        name=name,
        day_schedules=day_schedules,
        required_attributes=requires or [],
        is_event=is_event,
        display_order=order,
    )
    db_session.add(pos)
    await db_session.flush()
    return pos


def _all_days(start, end):
    return {str(d): {"start": start, "end": end} for d in range(7)}


def _weekdays(start, end):
    return {str(d): {"start": start, "end": end} for d in range(5)}  # א'–ה' (0..4)


# ── WeekProfileService ────────────────────────────────────────────────

class TestWeekProfileService:
    async def test_default_fallback_when_unassigned(self, db_session):
        await _make_profile(db_session, name="שגרה", is_default=True)
        week = await _make_week(db_session)
        profile, is_fallback = await _wp_service(db_session).get_effective_profile(week.id)
        assert profile.name == "שגרה"
        assert is_fallback is True

    async def test_fallback_to_any_profile_when_no_default(self, db_session):
        # Regression: a profile exists but none is flagged is_default (e.g. the
        # default's flag was lost). The board must still resolve — degrade to the
        # first profile by display order — instead of raising ProfileNotFound.
        await _make_profile(db_session, name="שגרה", is_default=False)
        week = await _make_week(db_session)
        profile, is_fallback = await _wp_service(db_session).get_effective_profile(week.id)
        assert profile.name == "שגרה"
        assert is_fallback is True

    async def test_raises_only_when_no_profiles_at_all(self, db_session):
        week = await _make_week(db_session)
        with pytest.raises(ProfileNotFoundException):
            await _wp_service(db_session).get_effective_profile(week.id)

    async def test_explicit_assignment_wins(self, db_session):
        await _make_profile(db_session, name="שגרה", is_default=True)
        holiday = await _make_profile(db_session, name="חג")
        week = await _make_week(db_session)
        svc = _wp_service(db_session)
        await svc.set_profile(week.id, holiday.id)

        profile, is_fallback = await svc.get_effective_profile(week.id)
        assert profile.name == "חג"
        assert is_fallback is False

    async def test_set_profile_is_idempotent_upsert(self, db_session):
        await _make_profile(db_session, name="שגרה", is_default=True)
        p1 = await _make_profile(db_session, name="חג")
        p2 = await _make_profile(db_session, name="אירוע")
        week = await _make_week(db_session)
        svc = _wp_service(db_session)
        await svc.set_profile(week.id, p1.id)
        await svc.set_profile(week.id, p2.id)  # replaces, no unique violation

        profile, _ = await svc.get_effective_profile(week.id)
        assert profile.name == "אירוע"

    async def test_set_profile_unknown_week_raises(self, db_session):
        profile = await _make_profile(db_session, name="שגרה", is_default=True)
        with pytest.raises(WeekNotFoundException):
            await _wp_service(db_session).set_profile(uuid.uuid4(), profile.id)

    async def test_set_profile_unknown_profile_raises(self, db_session):
        week = await _make_week(db_session)
        with pytest.raises(ProfileNotFoundException):
            await _wp_service(db_session).set_profile(week.id, uuid.uuid4())


# ── BoardService ──────────────────────────────────────────────────────

class TestBoardService:
    async def test_unknown_week_raises(self, db_session):
        with pytest.raises(WeekNotFoundException):
            await _board_service(db_session).resolve_board(uuid.uuid4())

    async def test_resolve_next_week_board_targets_upcoming_week(self, db_session):
        # The next week = upcoming Sunday→Saturday (same as the constraints flow).
        start, end = week_range(date.today())
        await _make_profile(db_session, name="שגרה", is_default=True)
        next_week = ScheduleWeek(
            start_date=start, end_date=end, status=WeekStatus.OPEN
        )
        db_session.add(next_week)
        await db_session.flush()

        board = await _board_service(db_session).resolve_next_week_board()
        assert board["week"].id == next_week.id
        assert board["days"][0]["date"] == start.isoformat()

    async def test_resolve_next_week_board_missing_raises(self, db_session):
        await _make_profile(db_session, name="שגרה", is_default=True)
        with pytest.raises(WeekNotFoundException):
            await _board_service(db_session).resolve_next_week_board()

    async def test_days_computed_from_week_start(self, db_session):
        await _make_profile(db_session, name="שגרה", is_default=True)
        week = await _make_week(db_session, start=date(2026, 7, 5))
        board = await _board_service(db_session).resolve_board(week.id)
        dates = [d["date"] for d in board["days"]]
        assert dates[0] == "2026-07-05"
        assert dates[6] == "2026-07-11"
        assert board["is_default_fallback"] is True

    async def test_band_derived_from_start_time(self, db_session):
        profile = await _make_profile(db_session, name="שגרה", is_default=True)
        week = await _make_week(db_session)
        # evening 19:00 (within [15:00,23:00)) -> evening, not night
        await _add_position(db_session, profile, "רכב סיור", _all_days("19:00", "07:00"))
        await _add_position(db_session, profile, "חמ\"ל לילה", _all_days("23:00", "07:00"))
        await _add_position(db_session, profile, "אחמ\"ש בוקר", _all_days("07:00", "15:00"))

        board = await _board_service(db_session).resolve_board(week.id)
        by_name = {r["name"]: r["band"] for r in board["rows"]}
        assert by_name["אחמ\"ש בוקר"] == "morning"
        assert by_name["רכב סיור"] == "evening"
        assert by_name["חמ\"ל לילה"] == "night"

    async def test_row_exposes_is_event(self, db_session):
        profile = await _make_profile(db_session, name="שגרה", is_default=True)
        week = await _make_week(db_session)
        await _add_position(db_session, profile, "ארנונה", _all_days("07:00", "15:00"))
        await _add_position(
            db_session, profile, "רענון", _all_days("07:00", "15:00"), is_event=True
        )
        board = await _board_service(db_session).resolve_board(week.id)
        by_name = {r["name"]: r["is_event"] for r in board["rows"]}
        assert by_name["ארנונה"] is False
        assert by_name["רענון"] is True

    async def test_row_order_band_then_display_order(self, db_session):
        profile = await _make_profile(db_session, name="שגרה", is_default=True)
        week = await _make_week(db_session)
        # All morning band. Within a band the manual display_order wins — even
        # though "alldays" has the most active days, it sits where its order says
        # (last), because the admin arranged the rows that way.
        await _add_position(db_session, profile, "single", {"5": {"start": "07:00", "end": "15:00"}}, order=0)
        await _add_position(db_session, profile, "weekdays", _weekdays("07:00", "15:00"), order=1)
        await _add_position(db_session, profile, "alldays", _all_days("07:00", "15:00"), order=2)
        # A later-band row confirms band still wins over display_order.
        await _add_position(db_session, profile, "night-all", _all_days("23:00", "07:00"), order=3)

        rows = await _board_service(db_session).resolve_board(week.id)
        names = [r["name"] for r in rows["rows"]]
        assert names == ["single", "weekdays", "alldays", "night-all"]

    async def test_cells_active_blocked_and_override(self, db_session):
        profile = await _make_profile(db_session, name="שגרה", is_default=True)
        week = await _make_week(db_session)
        # weekdays 07:00-15:00 except Thursday (idx 4) ends early -> override
        ds = _weekdays("07:00", "15:00")
        ds["4"] = {"start": "07:00", "end": "14:00"}
        await _add_position(db_session, profile, "ארנונה", ds)

        board = await _board_service(db_session).resolve_board(week.id)
        row = board["rows"][0]
        assert row["canonical_window"] == {"start": "07:00", "end": "15:00"}
        assert row["active_day_count"] == 5
        cells = row["cells"]
        assert cells[0]["active"] is True and cells[0]["is_override"] is False
        assert cells[4]["active"] is True and cells[4]["is_override"] is True
        assert cells[4]["window"] == {"start": "07:00", "end": "14:00"}
        assert cells[5]["active"] is False and cells[5]["window"] is None  # שישי blocked
