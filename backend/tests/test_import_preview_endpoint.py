"""Tests for POST /admin/import/constraints/preview (step 03, dry-run)."""

from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.constraints_import_controller import router
from app.dependencies import get_user_service, require_admin_role

FIXTURE = (
    Path(__file__).parent / "fixtures" / "דוגמה_אילוצים_מאבטחים.xlsx"
)
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _make_app(existing_names=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    user_svc = AsyncMock()
    user_svc.get_all_users.return_value = [
        type("U", (), {"full_name": n})() for n in (existing_names or [])
    ]
    app.dependency_overrides[get_user_service] = lambda: user_svc
    app.dependency_overrides[require_admin_role] = lambda: None
    return app


def _upload(client, data, filename="constraints.xlsx"):
    return client.post(
        "/admin/import/constraints/preview",
        files={"file": (filename, data, _XLSX_MIME)},
    )


def test_preview_sample_file_clean_output():
    app = _make_app(existing_names={"אבי כהן"})
    client = TestClient(app)
    resp = _upload(client, FIXTURE.read_bytes())
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["week_start"] == "2026-06-14"
    assert body["week_end"] == "2026-06-20"
    assert body["errors"] == []
    assert [g["name"] for g in body["guards"]] == [
        "אבי כהן", "בני לוי", "גדי מזרחי", "דנה אזולאי", "הראל ביטון",
    ]

    guards = {g["name"]: g for g in body["guards"]}

    # exists flag is informational: only אבי כהן is "known".
    assert guards["אבי כהן"]["exists"] is True
    assert guards["בני לוי"]["exists"] is False
    assert guards["אבי כהן"]["notes"] == "מעדיף משמרות בוקר"

    # דנה ראשון (day 0): morning 07:00–15:00 ∪ evening 15:00–23:00 → 07:00–23:00 / 16h
    dana_sun = guards["דנה אזולאי"]["days"][0]
    assert dana_sun["segments"] == ["07:00–23:00"]
    assert dana_sun["hours"] == 16.0

    # אבי שלישי (day 2): morning 07:00–13:00 + evening 15:00–19:00 → two windows, 10h
    avi_tue = guards["אבי כהן"]["days"][2]
    assert avi_tue["hours"] == 10.0
    assert avi_tue["shifts"]["morning"] == "07:00–13:00"
    assert avi_tue["shifts"]["afternoon"] == "15:00–19:00"


def test_preview_requires_admin():
    # No require_admin_role override → unauthenticated request is rejected.
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_service] = lambda: AsyncMock()
    client = TestClient(app)
    resp = _upload(client, FIXTURE.read_bytes())
    assert resp.status_code in (401, 403), resp.text


def test_preview_rejects_non_xlsx():
    app = _make_app()
    client = TestClient(app)
    resp = _upload(client, b"not a spreadsheet", filename="data.txt")
    assert resp.status_code == 400


def test_preview_corrupt_xlsx_is_400_not_500():
    app = _make_app()
    client = TestClient(app)
    resp = _upload(client, b"PK\x03\x04 garbage not really a zip", filename="bad.xlsx")
    assert resp.status_code == 400
