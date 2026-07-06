"""
Tests for the saved-schedule API (part B — frozen schedule snapshot).

Controller-layer tests with in-memory fake services (the real service + DB, incl.
the survives-profile-delete guarantee, are covered in
test_saved_schedule_service.py) and ``require_admin_role`` overridden.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_excel_export_service, require_admin_role
from app.exceptions import WeekNotFoundException
from app.schedule_builder.controllers.saved_schedule_controller import (
    router as saved_schedule_router,
)
from app.schedule_builder.dependencies import get_saved_schedule_service


def _saved(week_id=None, profile_name="שגרה", snapshot=None):
    return SimpleNamespace(
        week_id=week_id or uuid.uuid4(),
        profile_name=profile_name,
        updated_at=datetime(2026, 7, 1, 12, 0, 0),
        snapshot=snapshot or {"rows": []},
    )


class FakeSavedScheduleService:
    def __init__(self, rows=None, saved=None, error=None, get_result="unset"):
        self._rows = rows or []
        self._saved = saved
        self._error = error
        self._get_result = get_result

    async def save(self, week_id):
        if self._error:
            raise self._error
        return self._saved or _saved(week_id)

    async def list_all(self):
        return self._rows

    async def get(self, week_id):
        if self._get_result != "unset":
            return self._get_result
        return _saved(week_id)


class FakeExportService:
    def render_saved_schedule(self, snapshot):
        return b"xlsx-bytes"


def _make_client(service=None, export_service=None):
    app = FastAPI()
    app.include_router(saved_schedule_router)
    app.dependency_overrides[require_admin_role] = lambda: None
    if service is not None:
        app.dependency_overrides[get_saved_schedule_service] = lambda: service
    app.dependency_overrides[get_excel_export_service] = (
        lambda: export_service or FakeExportService()
    )
    return TestClient(app)


class TestSaveSchedule:
    def test_save_returns_metadata(self):
        week_id = uuid.uuid4()
        client = _make_client(service=FakeSavedScheduleService(saved=_saved(week_id)))
        resp = client.post(f"/admin/builder/weeks/{week_id}/save-schedule")
        assert resp.status_code == 200
        body = resp.json()
        assert body["week_id"] == str(week_id)
        assert body["profile_name"] == "שגרה"
        assert body["saved_at"].startswith("2026-07-01")

    def test_save_unknown_week_404(self):
        client = _make_client(
            service=FakeSavedScheduleService(error=WeekNotFoundException())
        )
        resp = client.post(f"/admin/builder/weeks/{uuid.uuid4()}/save-schedule")
        assert resp.status_code == 404


class TestListSavedSchedules:
    def test_list(self):
        w1, w2 = uuid.uuid4(), uuid.uuid4()
        rows = [_saved(w1, "שגרה"), _saved(w2, "חג")]
        client = _make_client(service=FakeSavedScheduleService(rows=rows))
        resp = client.get("/admin/builder/saved-schedules")
        assert resp.status_code == 200
        body = resp.json()
        assert {r["week_id"] for r in body} == {str(w1), str(w2)}


class TestDownloadSavedSchedule:
    def test_download_returns_xlsx(self):
        week_id = uuid.uuid4()
        client = _make_client(service=FakeSavedScheduleService(saved=_saved(week_id)))
        resp = client.get(f"/admin/builder/export/saved-schedule/{week_id}")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
        assert resp.content == b"xlsx-bytes"

    def test_download_missing_404(self):
        client = _make_client(
            service=FakeSavedScheduleService(get_result=None)
        )
        resp = client.get(f"/admin/builder/export/saved-schedule/{uuid.uuid4()}")
        assert resp.status_code == 404
