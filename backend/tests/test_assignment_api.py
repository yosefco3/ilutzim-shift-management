"""
Tests for the assignment API (part B — task 05, manual assignment).

Controller-layer tests with in-memory fake services (real services + DB are
covered in test_assignment_service.py) and ``require_admin_role`` overridden.
"""

import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import require_admin_role
from app.exceptions import (
    CellInactiveException,
    GuardAlreadyAssignedException,
    WeekNotFoundException,
)
from app.schedule_builder.controllers.assignment_controller import (
    router as assignment_router,
)
from app.schedule_builder.dependencies import (
    get_assignment_service,
    get_availability_service,
    get_board_service,
)


def _guard(full_name="נתן כהן", roles=("armed",)):
    return SimpleNamespace(id=uuid.uuid4(), full_name=full_name, roles=list(roles))


def _pool_guard(full_name="נתן כהן", roles=("armed",), **extra):
    """An enriched pool entry (dict) as returned by AvailabilityService."""
    return {
        "id": str(uuid.uuid4()),
        "full_name": full_name,
        "roles": list(roles),
        "notes": extra.get("notes"),
        "availability": extra.get("availability", {}),
        "available_hours": extra.get("available_hours", 0.0),
        "assigned_hours": extra.get("assigned_hours", 0.0),
        "remaining_hours": extra.get("remaining_hours", 0.0),
    }


def _assignment(user, position_id, day_index=0, segment=(None, None)):
    return SimpleNamespace(
        id=uuid.uuid4(),
        position_id=position_id,
        day_index=day_index,
        user_id=user.id,
        user=user,
        segment_start=segment[0],
        segment_end=segment[1],
    )


class FakeAvailabilityService:
    def __init__(self, guards=None, missing=False):
        self._guards = guards or []
        self._missing = missing

    async def build_pool(self, week_id, include_unsubmitted=None):
        if self._missing:
            raise WeekNotFoundException()
        return self._guards


class FakeAssignmentService:
    def __init__(self, rows=None, error=None):
        self._rows = rows or []
        self._error = error
        self.deleted = []

    async def list_for_week(self, week_id):
        if self._error:
            raise self._error
        return self._rows

    async def assign(self, week_id, position_id, day_index, user_id, ss=None, se=None):
        if self._error:
            raise self._error
        guard = _guard()
        guard.id = user_id
        return _assignment(guard, position_id, day_index, (ss, se))

    async def unassign(self, assignment_id):
        self.deleted.append(assignment_id)
        return assignment_id != _MISSING_ID


_MISSING_ID = uuid.uuid4()


class FakeBoardService:
    def __init__(self, board):
        self._board = board

    async def resolve_board(self, week_id):
        return self._board


def _make_client(pool_service=None, assignment_service=None, board_service=None):
    app = FastAPI()
    app.include_router(assignment_router)
    app.dependency_overrides[require_admin_role] = lambda: None
    if pool_service is not None:
        app.dependency_overrides[get_availability_service] = lambda: pool_service
    if assignment_service is not None:
        app.dependency_overrides[get_assignment_service] = lambda: assignment_service
    if board_service is not None:
        app.dependency_overrides[get_board_service] = lambda: board_service
    return TestClient(app)


class TestPoolAPI:
    def test_get_pool(self):
        guards = [
            _pool_guard("נתן כהן", ["armed"], remaining_hours=12.0,
                        availability={"0": [{"start": "07:00", "end": "19:00"}]},
                        notes="עדיפות לבקרים"),
            _pool_guard("רון לוי", []),
        ]
        client = _make_client(pool_service=FakeAvailabilityService(guards))
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/pool")
        assert resp.status_code == 200
        body = resp.json()
        assert [g["full_name"] for g in body] == ["נתן כהן", "רון לוי"]
        assert body[0]["roles"] == ["armed"]
        assert body[0]["remaining_hours"] == 12.0
        assert body[0]["availability"]["0"][0]["start"] == "07:00"
        assert body[0]["notes"] == "עדיפות לבקרים"

    def test_get_pool_unknown_week_404(self):
        client = _make_client(pool_service=FakeAvailabilityService(missing=True))
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/pool")
        assert resp.status_code == 404


class TestAssignmentAPI:
    def test_list_assignments(self):
        guard = _guard()
        rows = [_assignment(guard, uuid.uuid4(), 0)]
        client = _make_client(assignment_service=FakeAssignmentService(rows))
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/assignments")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["user_full_name"] == "נתן כהן"
        assert body[0]["user_roles"] == ["armed"]

    def test_create_assignment(self):
        client = _make_client(assignment_service=FakeAssignmentService())
        position_id = uuid.uuid4()
        user_id = uuid.uuid4()
        resp = client.post(
            f"/admin/builder/weeks/{uuid.uuid4()}/assignments",
            json={"position_id": str(position_id), "day_index": 2, "user_id": str(user_id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["day_index"] == 2
        assert body["user_id"] == str(user_id)

    def test_create_assignment_with_segment(self):
        client = _make_client(assignment_service=FakeAssignmentService())
        resp = client.post(
            f"/admin/builder/weeks/{uuid.uuid4()}/assignments",
            json={
                "position_id": str(uuid.uuid4()),
                "day_index": 0,
                "user_id": str(uuid.uuid4()),
                "segment_start": "19:00",
                "segment_end": "01:00",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["segment_start"] == "19:00"

    def test_create_bad_day_index_422(self):
        client = _make_client(assignment_service=FakeAssignmentService())
        resp = client.post(
            f"/admin/builder/weeks/{uuid.uuid4()}/assignments",
            json={"position_id": str(uuid.uuid4()), "day_index": 9, "user_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422

    def test_create_inactive_cell_422(self):
        svc = FakeAssignmentService(error=CellInactiveException())
        client = _make_client(assignment_service=svc)
        resp = client.post(
            f"/admin/builder/weeks/{uuid.uuid4()}/assignments",
            json={"position_id": str(uuid.uuid4()), "day_index": 0, "user_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422

    def test_create_duplicate_guard_409(self):
        svc = FakeAssignmentService(error=GuardAlreadyAssignedException())
        client = _make_client(assignment_service=svc)
        resp = client.post(
            f"/admin/builder/weeks/{uuid.uuid4()}/assignments",
            json={"position_id": str(uuid.uuid4()), "day_index": 0, "user_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 409

    def test_delete_assignment(self):
        svc = FakeAssignmentService()
        client = _make_client(assignment_service=svc)
        aid = uuid.uuid4()
        resp = client.delete(f"/admin/builder/assignments/{aid}")
        assert resp.status_code == 204
        assert svc.deleted == [aid]

    def test_delete_missing_404(self):
        svc = FakeAssignmentService()
        client = _make_client(assignment_service=svc)
        resp = client.delete(f"/admin/builder/assignments/{_MISSING_ID}")
        assert resp.status_code == 404


class TestWarningsAPI:
    def _board_one_cell(self, pos_id, required_attributes=None):
        cells = [{
            "day_index": 0, "active": True,
            "window": {"start": "07:00", "end": "15:00"}, "is_override": False,
        }]
        cells += [{"day_index": d, "active": False, "window": None, "is_override": False}
                  for d in range(1, 7)]
        return {"rows": [{
            "position_id": pos_id, "name": "ארנונה", "band": "morning",
            "required_attributes": required_attributes or [],
            "is_event": False, "event_required_count": None, "cells": cells,
        }]}

    def test_get_warnings_structure_and_rules(self):
        pos_id = uuid.uuid4()
        user = _guard(roles=[])  # holds no attribute → missing_attribute
        board = self._board_one_cell(pos_id, required_attributes=["armed"])
        pool = [_pool_guard()]
        pool[0]["id"] = user.id  # match the assignment's guard
        pool[0]["roles"] = []
        pool[0]["availability"] = {"0": [{"start": "19:00", "end": "23:00"}]}  # out of window
        rows = [_assignment(user, pos_id, 0)]
        client = _make_client(
            pool_service=FakeAvailabilityService(pool),
            assignment_service=FakeAssignmentService(rows),
            board_service=FakeBoardService(board),
        )
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/warnings")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"by_cell", "by_guard", "summary"}
        key = f"{pos_id}:0"
        types = {w["type"] for w in body["by_cell"][key]}
        assert "out_of_availability" in types
        assert "missing_attribute" in types
        assert body["summary"]["total"] >= 2

    def test_get_warnings_clean_board_is_empty(self):
        pos_id = uuid.uuid4()
        user = _guard(roles=["armed"])
        board = self._board_one_cell(pos_id, required_attributes=["armed"])
        pool = [_pool_guard()]
        pool[0]["id"] = user.id
        pool[0]["roles"] = ["armed"]
        pool[0]["availability"] = {"0": [{"start": "07:00", "end": "15:00"}]}
        rows = [_assignment(user, pos_id, 0)]
        client = _make_client(
            pool_service=FakeAvailabilityService(pool),
            assignment_service=FakeAssignmentService(rows),
            board_service=FakeBoardService(board),
        )
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/warnings")
        assert resp.status_code == 200
        assert resp.json()["summary"]["total"] == 0

    def test_get_warnings_requires_admin(self):
        from fastapi import HTTPException

        def _forbidden():
            raise HTTPException(status_code=403, detail="forbidden")

        app = FastAPI()
        app.include_router(assignment_router)
        app.dependency_overrides[require_admin_role] = _forbidden
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/warnings")
        assert resp.status_code == 403
