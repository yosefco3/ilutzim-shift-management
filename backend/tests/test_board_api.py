"""
Tests for the board API (part B — task 04).

Controller-layer tests with in-memory fake services (the real services + DB are
covered in test_board_service.py) and ``require_admin_role`` overridden.
"""

import uuid
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import require_admin_role
from app.exceptions import ProfileNotFoundException, WeekNotFoundException
from app.schedule_builder.controllers.board_controller import router as board_router
from app.schedule_builder.dependencies import (
    get_board_service,
    get_week_profile_service,
)

DEFAULT_PROFILE = SimpleNamespace(id=uuid.uuid4(), name="שגרה", is_default=True)
HOLIDAY_PROFILE = SimpleNamespace(id=uuid.uuid4(), name="חג", is_default=False)


class FakeWeekProfileService:
    def __init__(self, known_weeks=None):
        self._assignments: dict = {}
        self._known_weeks = known_weeks  # None = accept any

    async def get_effective_profile(self, week_id):
        prof = self._assignments.get(week_id)
        if prof is not None:
            return prof, False
        return DEFAULT_PROFILE, True

    async def set_profile(self, week_id, profile_id):
        if self._known_weeks is not None and week_id not in self._known_weeks:
            raise WeekNotFoundException()
        if profile_id != HOLIDAY_PROFILE.id:
            raise ProfileNotFoundException()
        self._assignments[week_id] = HOLIDAY_PROFILE
        return SimpleNamespace(week_id=week_id, profile_id=profile_id)


class FakeBoardService:
    def __init__(self, missing=False):
        self._missing = missing

    async def resolve_next_week_board(self):
        if self._missing:
            raise WeekNotFoundException("השבוע הבא טרם נוצר")
        return await self.resolve_board(uuid.uuid4())

    async def resolve_board(self, week_id):
        if self._missing:
            raise WeekNotFoundException()
        return {
            "week": SimpleNamespace(
                id=week_id,
                start_date=date(2026, 7, 5),
                end_date=date(2026, 7, 11),
                status="OPEN",
            ),
            "profile": DEFAULT_PROFILE,
            "is_default_fallback": True,
            "days": [
                {"index": i, "date": f"2026-07-{5 + i:02d}"} for i in range(7)
            ],
            "rows": [
                {
                    "position_id": uuid.uuid4(),
                    "name": "ארנונה",
                    "band": "morning",
                    "canonical_window": {"start": "07:00", "end": "15:00"},
                    "required_attributes": ["armed"],
                    "active_day_count": 5,
                    "cells": [
                        {
                            "day_index": d,
                            "active": d < 5,
                            "window": {"start": "07:00", "end": "15:00"} if d < 5 else None,
                            "is_override": False,
                        }
                        for d in range(7)
                    ],
                }
            ],
        }


def _make_client(wp_service=None, board_service=None):
    app = FastAPI()
    app.include_router(board_router)
    app.dependency_overrides[require_admin_role] = lambda: None
    if wp_service is not None:
        app.dependency_overrides[get_week_profile_service] = lambda: wp_service
    if board_service is not None:
        app.dependency_overrides[get_board_service] = lambda: board_service
    return TestClient(app)


class TestBoardAPI:
    def test_get_profile_default_fallback(self):
        client = _make_client(wp_service=FakeWeekProfileService())
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["profile"]["name"] == "שגרה"
        assert body["is_default_fallback"] is True

    def test_put_profile_then_effective(self):
        week_id = uuid.uuid4()
        svc = FakeWeekProfileService(known_weeks={week_id})
        client = _make_client(wp_service=svc)
        resp = client.put(
            f"/admin/builder/weeks/{week_id}/profile",
            json={"profile_id": str(HOLIDAY_PROFILE.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["profile"]["name"] == "חג"
        assert body["is_default_fallback"] is False

    def test_put_profile_unknown_week_404(self):
        svc = FakeWeekProfileService(known_weeks=set())
        client = _make_client(wp_service=svc)
        resp = client.put(
            f"/admin/builder/weeks/{uuid.uuid4()}/profile",
            json={"profile_id": str(HOLIDAY_PROFILE.id)},
        )
        assert resp.status_code == 404

    def test_put_profile_unknown_profile_404(self):
        week_id = uuid.uuid4()
        svc = FakeWeekProfileService(known_weeks={week_id})
        client = _make_client(wp_service=svc)
        resp = client.put(
            f"/admin/builder/weeks/{week_id}/profile",
            json={"profile_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_get_board_shape(self):
        client = _make_client(board_service=FakeBoardService())
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/board")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["days"]) == 7
        assert body["days"][0]["date"] == "2026-07-05"
        row = body["rows"][0]
        assert row["name"] == "ארנונה"
        assert row["band"] == "morning"
        assert len(row["cells"]) == 7
        assert row["cells"][5]["active"] is False

    def test_get_board_unknown_week_404(self):
        client = _make_client(board_service=FakeBoardService(missing=True))
        resp = client.get(f"/admin/builder/weeks/{uuid.uuid4()}/board")
        assert resp.status_code == 404

    def test_get_next_week_board(self):
        client = _make_client(board_service=FakeBoardService())
        resp = client.get("/admin/builder/board/next")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["days"]) == 7
        assert body["rows"][0]["name"] == "ארנונה"

    def test_get_next_week_board_missing_404(self):
        client = _make_client(board_service=FakeBoardService(missing=True))
        resp = client.get("/admin/builder/board/next")
        assert resp.status_code == 404
