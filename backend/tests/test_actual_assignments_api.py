"""
Step 05 — actual-board assignment editing: free editing with NO time gate,
structural rules only, and the soft-warning computation.

Service-level tests run on the real (in-memory) DB; a thin controller check
verifies the HTTP wiring with dependency overrides.
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.constants import WeekStatus
from app.dependencies import require_admin_role
from app.exceptions import (
    AssignmentNotFoundException,
    CellInactiveException,
    GuardAlreadyAssignedException,
    PositionNotFoundException,
)
from app.models.schedule_week import ScheduleWeek
from app.models.user import User
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.controllers.actual_schedule_controller import (
    router as actual_router,
)
from app.schedule_builder.dependencies import get_actual_schedule_service
from app.schedule_builder.models import ActualPosition, ActualSchedule
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
from app.schedule_builder.services.actual_schedule_service import (
    ActualScheduleNotAvailableException,
    ActualScheduleService,
)
from app.schedule_builder.services.week_profile_service import WeekProfileService
from app.utils.date_utils import today_il


def _service(session) -> ActualScheduleService:
    return ActualScheduleService(
        ActualScheduleRepository(session),
        ScheduleWeekRepository(session),
        WeekProfileService(
            WeekProfileRepository(session),
            ProfileRepository(session),
            ScheduleWeekRepository(session),
        ),
        PositionRepository(session),
        AssignmentRepository(session),
    )


async def _started_week(db_session, *, weeks_ago=1):
    start = today_il() - timedelta(days=7 * weeks_ago)
    week = ScheduleWeek(
        start_date=start, end_date=start + timedelta(days=6),
        status=WeekStatus.LOCKED,
    )
    db_session.add(week)
    await db_session.flush()
    return week


async def _bare_actual(db_session, week, *, day_schedules=None):
    """An actual schedule with one position (no planned layer needed)."""
    actual = ActualSchedule(week_id=week.id)
    db_session.add(actual)
    await db_session.flush()
    position = ActualPosition(
        actual_schedule_id=actual.id,
        name="שער ראשי",
        day_schedules=day_schedules
        or {"0": {"start": "07:00", "end": "15:00"},
            "1": {"start": "07:00", "end": "15:00"}},
    )
    db_session.add(position)
    await db_session.commit()
    return actual, position


async def _guard(db_session, name="נתן", *, is_active=True):
    guard = User(
        phone_number=f"05{uuid.uuid4().hex[:8]}",
        first_name=name, last_name="כהן", is_active=is_active,
    )
    db_session.add(guard)
    await db_session.commit()
    return guard


# ── Service-level: the free-editing contract ─────────────────────────────────


@pytest.mark.asyncio
async def test_assign_and_unassign_on_a_long_finished_week(db_session):
    """No time gate: a week that ended a month ago is editable."""
    week = await _started_week(db_session, weeks_ago=5)
    _, position = await _bare_actual(db_session, week)
    guard = await _guard(db_session)

    service = _service(db_session)
    assignment = await service.assign(position.id, 0, guard.id)
    assert assignment.user.full_name == guard.full_name

    await service.unassign(assignment.id)
    with pytest.raises(AssignmentNotFoundException):
        await service.unassign(assignment.id)


@pytest.mark.asyncio
async def test_third_guard_in_cell_is_allowed_with_warning(db_session):
    """No two-guard cap — but the board flags the cell as overstaffed."""
    week = await _started_week(db_session)
    _, position = await _bare_actual(db_session, week)
    service = _service(db_session)

    for name in ("א", "ב", "ג"):
        guard = await _guard(db_session, name)
        await service.assign(position.id, 0, guard.id)

    board = await service.get_board(week.id)
    overstaffed = [w for w in board["warnings"] if w["type"] == "overstaffed_cell"]
    assert len(overstaffed) == 1
    assert overstaffed[0]["count"] == 3
    assert len(board["assignments"]) == 3


@pytest.mark.asyncio
async def test_inactive_guard_may_be_assigned(db_session):
    """Retro reality: a deactivated guard did work — record it."""
    week = await _started_week(db_session)
    _, position = await _bare_actual(db_session, week)
    guard = await _guard(db_session, is_active=False)

    assignment = await _service(db_session).assign(position.id, 0, guard.id)
    assert assignment.id is not None


@pytest.mark.asyncio
async def test_structural_rules_still_hold(db_session):
    week = await _started_week(db_session)
    actual, position = await _bare_actual(db_session, week)
    guard = await _guard(db_session)
    service = _service(db_session)
    # Plain ids — the IntegrityError rollback below expires the ORM objects.
    position_id, guard_id = position.id, guard.id

    # Inactive day (no window for day 5).
    with pytest.raises(CellInactiveException):
        await service.assign(position_id, 5, guard_id)

    # Same guard twice in one cell.
    await service.assign(position_id, 0, guard_id)
    with pytest.raises(GuardAlreadyAssignedException):
        await service.assign(position_id, 0, guard_id, "13:00", "15:00")

    # Unknown position / cross-schedule position.
    with pytest.raises(PositionNotFoundException):
        await service.assign(uuid.uuid4(), 0, guard_id)
    with pytest.raises(PositionNotFoundException):
        await service.assign(
            position_id, 1, guard_id, expected_schedule_id=uuid.uuid4()
        )


@pytest.mark.asyncio
async def test_update_segment_and_overlap_warning(db_session):
    week = await _started_week(db_session)
    actual, position = await _bare_actual(db_session, week)
    other = ActualPosition(
        actual_schedule_id=actual.id, name="סייר",
        day_schedules={"0": {"start": "12:00", "end": "19:00"}},
    )
    db_session.add(other)
    await db_session.commit()

    guard = await _guard(db_session)
    service = _service(db_session)
    a1 = await service.assign(position.id, 0, guard.id)  # 07–15
    await service.assign(other.id, 0, guard.id)          # 12–19 → overlap

    board = await service.get_board(week.id)
    overlaps = [w for w in board["warnings"] if w["type"] == "already_in_shift"]
    assert len(overlaps) == 1
    assert overlaps[0]["position_names"] == ["סייר", "שער ראשי"]

    # Trimming the first shift to 07–12 clears the overlap.
    await service.update_segment(a1.id, "07:00", "12:00")
    board = await service.get_board(week.id)
    assert not [w for w in board["warnings"] if w["type"] == "already_in_shift"]


@pytest.mark.asyncio
async def test_editing_actual_never_touches_planning_tables(db_session):
    week = await _started_week(db_session)
    _, position = await _bare_actual(db_session, week)
    guard = await _guard(db_session)

    await _service(db_session).assign(position.id, 0, guard.id)
    planned = await AssignmentRepository(db_session).list_for_week(week.id)
    assert planned == []


# ── Controller-level: HTTP wiring ────────────────────────────────────────────


class FakeActualService:
    def __init__(self):
        self.week_id = uuid.uuid4()
        self.schedule_id = uuid.uuid4()
        self.position_id = uuid.uuid4()
        guard = SimpleNamespace(
            full_name="נתן כהן", roles=["ARMED"],
        )
        self.assignment = SimpleNamespace(
            id=uuid.uuid4(), actual_position_id=self.position_id,
            day_index=0, user_id=uuid.uuid4(), user=guard,
            segment_start=None, segment_end=None,
        )

    async def ensure_for_week(self, week_id, **_):
        if week_id != self.week_id:
            raise ActualScheduleNotAvailableException()
        return SimpleNamespace(id=self.schedule_id)

    async def assign(self, *args, **kwargs):
        return self.assignment

    async def unassign(self, assignment_id):
        return None


def _client(fake) -> TestClient:
    app = FastAPI()
    app.include_router(actual_router)
    app.dependency_overrides[require_admin_role] = lambda: None
    app.dependency_overrides[get_actual_schedule_service] = lambda: fake
    return TestClient(app)


def test_http_create_and_delete_assignment():
    fake = FakeActualService()
    client = _client(fake)

    response = client.post(
        f"/admin/actual/{fake.week_id}/assignments",
        json={
            "actual_position_id": str(fake.position_id),
            "day_index": 0,
            "user_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201
    assert response.json()["user_full_name"] == "נתן כהן"

    response = client.delete(f"/admin/actual/assignments/{fake.assignment.id}")
    assert response.status_code == 204


def test_http_future_week_rejected_with_409():
    fake = FakeActualService()
    client = _client(fake)

    response = client.post(
        f"/admin/actual/{uuid.uuid4()}/assignments",  # not the started week
        json={
            "actual_position_id": str(fake.position_id),
            "day_index": 0,
            "user_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 409
    assert "טרם התחיל" in response.json()["detail"]


def test_http_segment_validation_applies():
    fake = FakeActualService()
    client = _client(fake)

    response = client.post(
        f"/admin/actual/{fake.week_id}/assignments",
        json={
            "actual_position_id": str(fake.position_id),
            "day_index": 0,
            "user_id": str(uuid.uuid4()),
            "segment_start": "7pm",
            "segment_end": "23:00",
        },
    )
    assert response.status_code == 422
