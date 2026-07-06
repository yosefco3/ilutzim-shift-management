"""
Tests for the positions API (part B — schedule builder).

Controller-layer tests with an in-memory fake service (the real service+DB is
covered in test_position_service.py) and ``require_admin_role`` overridden.
"""

import uuid
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import require_admin_role
from app.exceptions import (
    PositionNotFoundException,
    PositionReorderMismatchException,
    ProfileNotFoundException,
)
from app.schedule_builder.controllers.position_controller import router as position_router
from app.schedule_builder.dependencies import get_position_service
from app.schedule_builder.models.position import Position

VALID_SCHEDULE = {"0": {"start": "07:30", "end": "15:00"}}


class FakePositionService:
    def __init__(self):
        self._positions: list[Position] = []
        # Target profile ids that copy_position should treat as nonexistent.
        self._missing_profiles: set = set()

    def _make(self, profile_id, name, day_schedules, required_attributes, is_event=False,
              event_required_count=None):
        p = Position(
            profile_id=profile_id, name=name,
            day_schedules=day_schedules or {},
            required_attributes=required_attributes or [],
            is_event=bool(is_event),
            event_required_count=event_required_count if is_event else None,
            display_order=len(self._positions),
        )
        p.id = uuid.uuid4()
        p.created_at = datetime(2026, 1, 1)
        return p

    async def list_positions(self, profile_id):
        return [p for p in self._positions if p.profile_id == profile_id]

    async def create_position(self, profile_id, name, day_schedules=None, required_attributes=None, is_event=False,
                              event_required_count=None):
        p = self._make(profile_id, name, day_schedules, required_attributes, is_event,
                       event_required_count)
        self._positions.append(p)
        return p

    def _find(self, pid):
        for p in self._positions:
            if p.id == pid:
                return p
        raise PositionNotFoundException()

    async def get_position(self, pid):
        return self._find(pid)

    async def update_position(self, pid, name=None, day_schedules=None, required_attributes=None, is_event=None,
                              event_required_count=None):
        p = self._find(pid)
        if name is not None:
            p.name = name
        if day_schedules is not None:
            p.day_schedules = day_schedules
        if required_attributes is not None:
            p.required_attributes = required_attributes
        if is_event is not None:
            p.is_event = bool(is_event)
            p.event_required_count = event_required_count if bool(is_event) else None
        elif event_required_count is not None:
            p.event_required_count = event_required_count
        return p

    async def delete_position(self, pid):
        self._positions.remove(self._find(pid))

    async def reorder_positions(self, profile_id, ordered_ids):
        in_profile = [p for p in self._positions if p.profile_id == profile_id]
        if set(ordered_ids) != {p.id for p in in_profile}:
            raise PositionReorderMismatchException()
        by_id = {p.id: p for p in in_profile}
        ordered = [by_id[i] for i in ordered_ids]
        for order, p in enumerate(ordered):
            p.display_order = order
        return ordered

    async def copy_position(self, pid, target_profile_id):
        src = self._find(pid)
        if target_profile_id in self._missing_profiles:
            raise ProfileNotFoundException()
        copy = self._make(
            target_profile_id, src.name,
            dict(src.day_schedules), list(src.required_attributes),
            src.is_event, src.event_required_count,
        )
        self._positions.append(copy)
        return copy


def _make_client(service):
    app = FastAPI()
    app.include_router(position_router)
    app.dependency_overrides[get_position_service] = lambda: service
    app.dependency_overrides[require_admin_role] = lambda: None
    return TestClient(app)


class TestPositionAPI:
    def test_create_then_list(self):
        svc = FakePositionService()
        client = _make_client(svc)
        profile_id = uuid.uuid4()

        resp = client.post(
            f"/admin/builder/profiles/{profile_id}/positions",
            json={"name": "ארנונה",
                  "day_schedules": VALID_SCHEDULE, "required_attributes": ["armed"]},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "ארנונה"
        assert body["day_schedules"] == VALID_SCHEDULE
        assert body["required_attributes"] == ["armed"]

        resp = client.get(f"/admin/builder/profiles/{profile_id}/positions")
        assert [p["name"] for p in resp.json()] == ["ארנונה"]

    def test_create_bad_day_index_422(self):
        client = _make_client(FakePositionService())
        resp = client.post(
            f"/admin/builder/profiles/{uuid.uuid4()}/positions",
            json={"name": "x",
                  "day_schedules": {"9": {"start": "07:00", "end": "15:00"}}},
        )
        assert resp.status_code == 422

    def test_create_bad_time_422(self):
        client = _make_client(FakePositionService())
        resp = client.post(
            f"/admin/builder/profiles/{uuid.uuid4()}/positions",
            json={"name": "x",
                  "day_schedules": {"0": {"start": "25:00", "end": "15:00"}}},
        )
        assert resp.status_code == 422

    def test_create_empty_schedule_422(self):
        client = _make_client(FakePositionService())
        resp = client.post(
            f"/admin/builder/profiles/{uuid.uuid4()}/positions",
            json={"name": "x", "day_schedules": {}},
        )
        assert resp.status_code == 422

    def test_night_wrap_allowed(self):
        client = _make_client(FakePositionService())
        resp = client.post(
            f"/admin/builder/profiles/{uuid.uuid4()}/positions",
            json={"name": "רכב סיור",
                  "day_schedules": {"0": {"start": "23:00", "end": "07:00"}}},
        )
        assert resp.status_code == 201

    def test_patch_updates(self):
        svc = FakePositionService()
        p = svc._make(uuid.uuid4(), "ארנונה", VALID_SCHEDULE, [])
        svc._positions.append(p)
        client = _make_client(svc)
        resp = client.patch(f"/admin/builder/positions/{p.id}", json={"name": "ארנונה ב"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "ארנונה ב"

    def test_patch_empty_422(self):
        svc = FakePositionService()
        p = svc._make(uuid.uuid4(), "ארנונה", VALID_SCHEDULE, [])
        svc._positions.append(p)
        client = _make_client(svc)
        resp = client.patch(f"/admin/builder/positions/{p.id}", json={})
        assert resp.status_code == 422

    def test_get_missing_404(self):
        client = _make_client(FakePositionService())
        resp = client.get(f"/admin/builder/positions/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_ok(self):
        svc = FakePositionService()
        p = svc._make(uuid.uuid4(), "ארנונה", VALID_SCHEDULE, [])
        svc._positions.append(p)
        client = _make_client(svc)
        resp = client.delete(f"/admin/builder/positions/{p.id}")
        assert resp.status_code == 204

    def test_copy_to_profile_201(self):
        svc = FakePositionService()
        p = svc._make(uuid.uuid4(), "ארנונה", VALID_SCHEDULE, ["armed"])
        svc._positions.append(p)
        client = _make_client(svc)
        target = uuid.uuid4()

        resp = client.post(
            f"/admin/builder/positions/{p.id}/copy",
            json={"target_profile_id": str(target)},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["profile_id"] == str(target)
        assert body["name"] == "ארנונה"
        assert body["day_schedules"] == VALID_SCHEDULE
        assert body["id"] != str(p.id)

    def test_copy_missing_source_404(self):
        client = _make_client(FakePositionService())
        resp = client.post(
            f"/admin/builder/positions/{uuid.uuid4()}/copy",
            json={"target_profile_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_copy_missing_target_profile_404(self):
        svc = FakePositionService()
        p = svc._make(uuid.uuid4(), "ארנונה", VALID_SCHEDULE, [])
        svc._positions.append(p)
        target = uuid.uuid4()
        svc._missing_profiles.add(target)
        client = _make_client(svc)
        resp = client.post(
            f"/admin/builder/positions/{p.id}/copy",
            json={"target_profile_id": str(target)},
        )
        assert resp.status_code == 404

    def test_copy_bad_uuid_422(self):
        svc = FakePositionService()
        p = svc._make(uuid.uuid4(), "ארנונה", VALID_SCHEDULE, [])
        svc._positions.append(p)
        client = _make_client(svc)
        resp = client.post(
            f"/admin/builder/positions/{p.id}/copy",
            json={"target_profile_id": "not-a-uuid"},
        )
        assert resp.status_code == 422


class TestPositionReorderAPI:
    def test_reorder_returns_new_order(self):
        svc = FakePositionService()
        profile_id = uuid.uuid4()
        a = svc._make(profile_id, "א", VALID_SCHEDULE, [])
        b = svc._make(profile_id, "ב", VALID_SCHEDULE, [])
        c = svc._make(profile_id, "ג", VALID_SCHEDULE, [])
        svc._positions.extend([a, b, c])
        client = _make_client(svc)

        resp = client.put(
            f"/admin/builder/profiles/{profile_id}/positions/order",
            json={"position_ids": [str(c.id), str(a.id), str(b.id)]},
        )
        assert resp.status_code == 200
        assert [p["name"] for p in resp.json()] == ["ג", "א", "ב"]

    def test_reorder_mismatch_400(self):
        svc = FakePositionService()
        profile_id = uuid.uuid4()
        a = svc._make(profile_id, "א", VALID_SCHEDULE, [])
        b = svc._make(profile_id, "ב", VALID_SCHEDULE, [])
        svc._positions.extend([a, b])
        client = _make_client(svc)
        # Missing b -> not a full permutation.
        resp = client.put(
            f"/admin/builder/profiles/{profile_id}/positions/order",
            json={"position_ids": [str(a.id)]},
        )
        assert resp.status_code == 400

    def test_reorder_duplicate_ids_422(self):
        client = _make_client(FakePositionService())
        pid = str(uuid.uuid4())
        resp = client.put(
            f"/admin/builder/profiles/{uuid.uuid4()}/positions/order",
            json={"position_ids": [pid, pid]},
        )
        assert resp.status_code == 422

    def test_reorder_empty_422(self):
        client = _make_client(FakePositionService())
        resp = client.put(
            f"/admin/builder/profiles/{uuid.uuid4()}/positions/order",
            json={"position_ids": []},
        )
        assert resp.status_code == 422


class TestPositionAPIAuth:
    def test_requires_admin(self):
        app = FastAPI()
        app.include_router(position_router)
        app.dependency_overrides[get_position_service] = lambda: FakePositionService()
        client = TestClient(app)
        resp = client.get(f"/admin/builder/profiles/{uuid.uuid4()}/positions")
        assert resp.status_code in (401, 403)
