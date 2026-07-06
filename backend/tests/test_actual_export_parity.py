"""
Step 03 — the actual read model and its parity guarantee.

The central invariant: a freshly-seeded (unedited) actual schedule must read
EXACTLY like the planned schedule through the shared ``WeekSchedule`` core —
same rows, same placements, same merging, same gaps. Position *ids* differ by
design (the copy owns its rows), so comparison is by name.
"""

from datetime import timedelta

import pytest

from app.constants import WeekStatus
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.models.activation_profile import ActivationProfile
from app.schedule_builder.models.position import Position
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment
from app.schedule_builder.models.week_profile_assignment import WeekProfileAssignment
from app.schedule_builder.repositories.actual_schedule_repository import (
    ActualScheduleRepository,
)
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.repositories.week_profile_repository import (
    WeekProfileRepository,
)
from app.schedule_builder.services.actual_schedule_export_service import (
    ActualScheduleExportService,
)
from app.schedule_builder.services.actual_schedule_service import (
    ActualScheduleService,
)
from app.schedule_builder.services.assignment_service import AssignmentService
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.services.schedule_export_service import (
    ScheduleExportService,
)
from app.schedule_builder.services.week_profile_service import WeekProfileService
from app.utils.date_utils import today_il


def _week_profile_service(session) -> WeekProfileService:
    return WeekProfileService(
        WeekProfileRepository(session),
        ProfileRepository(session),
        ScheduleWeekRepository(session),
    )


def _planned_export(session) -> ScheduleExportService:
    return ScheduleExportService(
        BoardService(
            ScheduleWeekRepository(session),
            _week_profile_service(session),
            PositionRepository(session),
        ),
        AssignmentService(
            AssignmentRepository(session),
            ScheduleWeekRepository(session),
            PositionRepository(session),
        ),
        UserRepository(session),
    )


def _actual_service(session) -> ActualScheduleService:
    return ActualScheduleService(
        ActualScheduleRepository(session),
        ScheduleWeekRepository(session),
        _week_profile_service(session),
        PositionRepository(session),
        AssignmentRepository(session),
    )


def _actual_export(session) -> ActualScheduleExportService:
    return ActualScheduleExportService(
        _actual_service(session),
        ActualScheduleRepository(session),
        ScheduleWeekRepository(session),
        _planned_export(session),
        UserRepository(session),
    )


async def _make_rich_week(db_session, *, started=True):
    """A planned week exercising every read-model feature: segments, tiling,
    partial coverage (gaps), an event with a fixed count, and a night shift
    crossing midnight."""
    offset = -7 if started else 7
    start = today_il() + timedelta(days=offset)
    week = ScheduleWeek(
        start_date=start, end_date=start + timedelta(days=6),
        status=WeekStatus.LOCKED if started else WeekStatus.CLOSED,
    )
    db_session.add(week)
    await db_session.flush()

    profile = ActivationProfile(name="שגרה", is_default=True)
    db_session.add(profile)
    await db_session.flush()
    db_session.add(WeekProfileAssignment(week_id=week.id, profile_id=profile.id))

    arnona = Position(
        profile_id=profile.id, name="ארנונה",
        day_schedules={str(d): {"start": "07:00", "end": "19:00"} for d in range(6)},
        display_order=1,
    )
    night = Position(
        profile_id=profile.id, name="סייר לילה",
        day_schedules={str(d): {"start": "23:00", "end": "07:00"} for d in range(7)},
        display_order=2,
    )
    event = Position(
        profile_id=profile.id, name="ישיבת מועצה",
        day_schedules={"2": {"start": "17:00", "end": "21:00"}},
        display_order=3, is_event=True, event_required_count=4,
    )
    evening = Position(
        profile_id=profile.id, name="אחמש ערב",
        day_schedules={"4": {"start": "12:00", "end": "19:00"}},
        display_order=4,
    )
    db_session.add_all([arnona, night, event, evening])
    await db_session.flush()

    natan = User(phone_number="0501111111", first_name="נתן", last_name="כהן")
    dana = User(phone_number="0502222222", first_name="דנה", last_name="לוי")
    idle = User(phone_number="0503333333", first_name="רן", last_name="פנוי")
    db_session.add_all([natan, dana, idle])
    await db_session.flush()

    db_session.add_all([
        # Day 0: tiled cell — Natan 07–13, Dana 13–19 (full coverage).
        ScheduleAssignment(week_id=week.id, position_id=arnona.id, day_index=0,
                           user_id=natan.id, segment_start="07:00", segment_end="13:00"),
        ScheduleAssignment(week_id=week.id, position_id=arnona.id, day_index=0,
                           user_id=dana.id, segment_start="13:00", segment_end="19:00"),
        # Day 1: partial coverage — Natan 07–11 only (gap 11–19).
        ScheduleAssignment(week_id=week.id, position_id=arnona.id, day_index=1,
                           user_id=natan.id, segment_start="07:00", segment_end="11:00"),
        # Day 2: whole-window (no segment) + the event with two attendees.
        ScheduleAssignment(week_id=week.id, position_id=arnona.id, day_index=2,
                           user_id=dana.id),
        ScheduleAssignment(week_id=week.id, position_id=event.id, day_index=2,
                           user_id=natan.id),
        ScheduleAssignment(week_id=week.id, position_id=event.id, day_index=2,
                           user_id=dana.id),
        # Day 3: night shift crossing midnight (whole window 23:00–07:00).
        ScheduleAssignment(week_id=week.id, position_id=night.id, day_index=3,
                           user_id=natan.id),
        # Day 4: back-to-back run of the SAME guard across two positions —
        # by_guard must merge it to one 07–19 span with joined names.
        ScheduleAssignment(week_id=week.id, position_id=arnona.id, day_index=4,
                           user_id=dana.id, segment_start="07:00", segment_end="12:00"),
        ScheduleAssignment(week_id=week.id, position_id=evening.id, day_index=4,
                           user_id=dana.id),
    ])
    await db_session.commit()
    return week


def _normalize(schedule) -> dict:
    """WeekSchedule → an id-free comparable structure (names, not row ids)."""
    return {
        "days": schedule.days,
        "by_position": [
            {
                "name": row.name,
                "band": row.band,
                "canonical_window": row.canonical_window,
                "is_event": row.is_event,
                "event_required_count": row.event_required_count,
                "days": [
                    {
                        "day_index": d.day_index,
                        "active": d.active,
                        "placements": [
                            (p.user_name, p.start, p.end) for p in d.placements
                        ],
                        "gaps": d.gaps,
                    }
                    for d in row.days
                ],
            }
            for row in schedule.by_position
        ],
        "by_guard": [
            {
                "user_name": g.user_name,
                "shifts": [
                    (s.day_index, s.date, s.position_name, s.start, s.end, s.is_event)
                    for s in g.shifts
                ],
            }
            for g in schedule.by_guard
        ],
    }


@pytest.mark.asyncio
async def test_fresh_actual_reads_exactly_like_the_plan(db_session):
    week = await _make_rich_week(db_session)

    planned = await _planned_export(db_session).get_week_schedule(week.id)
    actual = await _actual_export(db_session).get_week_schedule(week.id)

    assert _normalize(actual) == _normalize(planned)
    # Sanity that the rich fixture actually exercised the features:
    norm = _normalize(planned)
    arnona = next(r for r in norm["by_position"] if r["name"] == "ארנונה")
    assert arnona["days"][1]["gaps"] == [("11:00", "19:00")]  # partial coverage
    assert len(arnona["days"][0]["placements"]) == 2  # tiling
    dana = next(g for g in norm["by_guard"] if "דנה" in g["user_name"])
    day4 = [s for s in dana["shifts"] if s[0] == 4]
    assert [(s[3], s[4]) for s in day4] == [("07:00", "19:00")]  # merged run
    assert day4[0][2] == "ארנונה / אחמש ערב"  # joined position names


@pytest.mark.asyncio
async def test_editing_actual_diverges_only_the_actual(db_session):
    week = await _make_rich_week(db_session)

    # Seed, then edit the copy directly: remove Natan's day-0 shift.
    actual = await _actual_service(db_session).ensure_for_week(week.id)
    repo = ActualScheduleRepository(db_session)
    assignments = await repo.list_assignments(actual.id)
    natan_day0 = next(
        a for a in assignments
        if a.day_index == 0 and a.segment_start == "07:00"
    )
    await db_session.delete(natan_day0)
    await db_session.commit()

    planned = await _planned_export(db_session).get_week_schedule(week.id)
    actual_schedule = await _actual_export(db_session).get_week_schedule(week.id)

    planned_arnona = next(r for r in planned.by_position if r.name == "ארנונה")
    actual_arnona = next(r for r in actual_schedule.by_position if r.name == "ארנונה")
    assert len(planned_arnona.days[0].placements) == 2  # plan untouched
    assert len(actual_arnona.days[0].placements) == 1
    assert actual_arnona.days[0].gaps == [("07:00", "13:00")]  # now a gap


@pytest.mark.asyncio
async def test_historical_week_seeds_lazily_on_read(db_session):
    week = await _make_rich_week(db_session)

    schedule = await _actual_export(db_session).get_week_schedule(week.id)
    assert len(schedule.by_position) == 4

    seeded = await ActualScheduleRepository(db_session).get_by_week(week.id)
    assert seeded is not None
    assert seeded.seed_source == "lazy"


@pytest.mark.asyncio
async def test_future_week_falls_back_to_the_plan(db_session):
    week = await _make_rich_week(db_session, started=False)

    schedule = await _actual_export(db_session).get_week_schedule(week.id)
    planned = await _planned_export(db_session).get_week_schedule(week.id)
    assert _normalize(schedule) == _normalize(planned)

    # And no actual copy was created for the future week.
    assert await ActualScheduleRepository(db_session).get_by_week(week.id) is None
