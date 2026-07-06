"""
Stage 3 / 01 — AttendanceEvent model, append-only repository, feature flag.
"""

import uuid
from datetime import datetime, timedelta

import pytest

from app.attendance.constants import PunchDirection, PunchSource
from app.attendance.models.attendance_event import AttendanceEvent
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.config import get_settings
from app.models.user import User


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _make_guard(db_session, phone="0501234567") -> User:
    user = User(
        phone_number=phone,
        first_name="יוסי",
        last_name="כהן",
        roles=[],
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------- model ----------

@pytest.mark.asyncio
async def test_event_roundtrip(db_session):
    guard = await _make_guard(db_session)
    repo = AttendanceEventRepository(db_session)

    punched = datetime(2026, 7, 5, 7, 12)
    event = await repo.add(
        user_id=guard.id,
        direction=PunchDirection.IN,
        punched_at=punched,
        source=PunchSource.TELEGRAM,
        lat=31.778,
        lng=35.235,
        accuracy_m=12.5,
        distance_from_site_m=44.0,
        out_of_radius=False,
    )
    await db_session.commit()

    loaded = await repo.get_by_id(event.id)
    assert loaded is not None
    assert loaded.user_id == guard.id
    assert loaded.direction == PunchDirection.IN
    assert loaded.source == PunchSource.TELEGRAM
    assert loaded.punched_at == punched
    assert loaded.out_of_radius is False
    assert loaded.note is None


@pytest.mark.asyncio
async def test_list_for_user_ordered_and_bounded(db_session):
    guard = await _make_guard(db_session)
    other = await _make_guard(db_session, phone="0507654321")
    repo = AttendanceEventRepository(db_session)

    base = datetime(2026, 7, 5, 7, 0)
    # out-of-order inserts; the query must return chronological order
    for offset, direction in [(8, PunchDirection.OUT), (0, PunchDirection.IN)]:
        await repo.add(
            user_id=guard.id,
            direction=direction,
            punched_at=base + timedelta(hours=offset),
            source=PunchSource.TELEGRAM,
        )
    # noise: another guard + an event outside the window
    await repo.add(
        user_id=other.id,
        direction=PunchDirection.IN,
        punched_at=base,
        source=PunchSource.TELEGRAM,
    )
    await repo.add(
        user_id=guard.id,
        direction=PunchDirection.IN,
        punched_at=base + timedelta(days=2),
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()

    events = await repo.list_for_user(
        guard.id, base - timedelta(hours=1), base + timedelta(hours=12)
    )
    assert [e.direction for e in events] == [PunchDirection.IN, PunchDirection.OUT]
    assert all(e.user_id == guard.id for e in events)


# ---------- dedup query ----------

@pytest.mark.asyncio
async def test_exists_similar_inside_and_outside_window(db_session):
    guard = await _make_guard(db_session)
    repo = AttendanceEventRepository(db_session)

    punched = datetime(2026, 7, 5, 7, 0)
    await repo.add(
        user_id=guard.id,
        direction=PunchDirection.IN,
        punched_at=punched,
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()

    # same direction, 3 minutes later, window 5 → found
    dup = await repo.exists_similar(
        guard.id, PunchDirection.IN, punched + timedelta(minutes=3), 5
    )
    assert dup is not None

    # other direction inside the window → not a duplicate
    assert (
        await repo.exists_similar(
            guard.id, PunchDirection.OUT, punched + timedelta(minutes=3), 5
        )
        is None
    )

    # same direction but beyond the window → not a duplicate
    assert (
        await repo.exists_similar(
            guard.id, PunchDirection.IN, punched + timedelta(minutes=9), 5
        )
        is None
    )


# ---------- append-only guarantees ----------

@pytest.mark.asyncio
async def test_raw_log_is_immutable(db_session):
    guard = await _make_guard(db_session)
    repo = AttendanceEventRepository(db_session)
    event = await repo.add(
        user_id=guard.id,
        direction=PunchDirection.IN,
        punched_at=datetime(2026, 7, 5, 7, 0),
        source=PunchSource.TELEGRAM,
    )
    await db_session.commit()

    with pytest.raises(RuntimeError):
        await repo.update(event.id, note="tampered")
    with pytest.raises(RuntimeError):
        await repo.delete(event.id)


# ---------- feature flag ----------

def _build_app(monkeypatch, enabled: bool):
    monkeypatch.setenv("ATTENDANCE_ENABLED", "true" if enabled else "false")
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    get_settings.cache_clear()  # don't leak the override into other tests
    return app


def _paths(app) -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


def test_attendance_routes_present_when_enabled(monkeypatch):
    paths = _paths(_build_app(monkeypatch, True))
    assert any("/admin/attendance" in p for p in paths)


def test_attendance_routes_absent_when_disabled(monkeypatch):
    paths = _paths(_build_app(monkeypatch, False))
    assert not any("/admin/attendance" in p for p in paths)
    # Core routes remain registered.
    assert "/health" in paths


def test_attendance_flag_defaults_off():
    """The CODE default is off (ships dormant) — checked on the model field so a
    local dev .env with ATTENDANCE_ENABLED=true doesn't break the assertion."""
    from app.config import Settings

    assert Settings.model_fields["ATTENDANCE_ENABLED"].default is False
