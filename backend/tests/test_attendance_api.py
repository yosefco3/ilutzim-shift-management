"""
Stage 3 / 02 step 2 — attendance REST endpoints (controller layer, fake service).
"""

import uuid
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.attendance.controllers.attendance_controller import router as attendance_router
from app.attendance.dependencies import (
    get_adjustment_service,
    get_comparison_service,
    get_event_repo,
)
from app.attendance.services.comparison_service import (
    ActualView,
    DaySummary,
    Segment,
    UserDayComparison,
)
from app.attendance.constants import ShiftPairStatus
from app.dependencies import require_admin_role

D = date(2026, 7, 5)
NOW = datetime(2026, 7, 5, 14, 30)
UID = uuid.uuid4()


def _row(band="morning", severity="ok", tag="תקין ✔"):
    return UserDayComparison(
        user_id=UID,
        user_name="יוסי כהן",
        date=D,
        band=band,
        planned=[],
        actual=[
            ActualView(
                shift_id=uuid.uuid4(),
                check_in_at=datetime(2026, 7, 5, 7, 2),
                check_out_raw=datetime(2026, 7, 5, 15, 1),
                check_out_rounded=datetime(2026, 7, 5, 15, 15),
                status=ShiftPairStatus.COMPLETE,
                in_source="telegram",
                out_source="telegram",
                out_of_radius=False,
            )
        ],
        segments=[
            Segment(datetime(2026, 7, 5, 7, 2), datetime(2026, 7, 5, 15, 1), "covered")
        ],
        summary=DaySummary(
            planned_minutes=480,
            actual_minutes=493,
            extra_minutes=0,
            delta_in_minutes=2,
            delta_out_minutes=1,
            severity=severity,
            tag=tag,
        ),
    )


class FakeComparison:
    async def get_day_all(self, day, *, now):
        return {
            "date": day,
            "now": now,
            "counters": {"scheduled": 2, "present": 1, "big": 1, "small": 0},
            "rows": [_row(), _row(band="night", severity="big", tag="לא הגיע")],
        }

    async def get_period_summary(self, date_from, date_to, *, now):
        return [
            {
                "user_id": UID,
                "user_name": "יוסי כהן",
                "planned_minutes": 2400,
                "actual_minutes": 2465,
                "extra_minutes": 65,
                "days_scheduled": 5,
                "days_present": 5,
                "big": 0,
                "small": 1,
            }
        ]

    async def get_user_period(self, user_id, date_from, date_to, *, now):
        return {
            "user_id": user_id,
            "user_name": "יוסי כהן",
            "from": date_from,
            "to": date_to,
            "days": [_row()],
            "summary": {"planned_minutes": 480, "actual_minutes": 493,
                        "extra_minutes": 0, "big": 0, "small": 0},
        }


def test_period_summary_endpoint():
    res = _client().get(
        "/admin/attendance/period-summary",
        params={"from": "2026-07-05", "to": "2026-07-11"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body[0]["user_name"] == "יוסי כהן"
    assert body[0]["big"] == 0


class FakeEventsRepo:
    async def count_since(self, from_dt):
        return 7

    async def last_event_at(self):
        return datetime(2026, 7, 5, 13, 3)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(attendance_router)
    app.dependency_overrides[require_admin_role] = lambda: None
    app.dependency_overrides[get_comparison_service] = lambda: FakeComparison()
    app.dependency_overrides[get_event_repo] = lambda: FakeEventsRepo()
    app.dependency_overrides[get_adjustment_service] = lambda: object()
    return TestClient(app)


def test_day_view_groups_by_band_and_counts():
    res = _client().get("/admin/attendance/day", params={"date": "2026-07-05"})
    assert res.status_code == 200
    body = res.json()
    assert body["date"] == "2026-07-05"
    assert body["counters"]["big"] == 1
    bands = {b["band"]: b["rows"] for b in body["bands"]}
    assert set(bands) == {"morning", "night"}
    # band order: morning before night; empty bands omitted
    assert [b["band"] for b in body["bands"]] == ["morning", "night"]
    row = bands["morning"][0]
    assert row["user_name"] == "יוסי כהן"
    assert row["actual"][0]["check_out_rounded"].endswith("15:15:00")
    assert row["actual"][0]["check_out_raw"].endswith("15:01:00")
    assert row["segments"][0]["kind"] == "covered"
    assert bands["night"][0]["summary"]["tag"] == "לא הגיע"


def test_day_view_defaults_to_today():
    res = _client().get("/admin/attendance/day")
    assert res.status_code == 200


def test_user_period_shape():
    res = _client().get(
        f"/admin/attendance/users/{UID}",
        params={"from": "2026-07-05", "to": "2026-07-11"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["date_from"] == "2026-07-05"
    assert body["days"][0]["summary"]["actual_minutes"] == 493


def test_user_period_validation():
    c = _client()
    # reversed range
    res = c.get(
        f"/admin/attendance/users/{UID}",
        params={"from": "2026-07-11", "to": "2026-07-05"},
    )
    assert res.status_code == 422
    # > 62 days
    res = c.get(
        f"/admin/attendance/users/{UID}",
        params={"from": "2026-01-01", "to": "2026-07-05"},
    )
    assert res.status_code == 422
    # bad date format
    res = c.get(
        f"/admin/attendance/users/{UID}",
        params={"from": "לא-תאריך", "to": "2026-07-05"},
    )
    assert res.status_code == 422


def test_manual_entry_validation():
    """Bad time format is a 422 before any service work happens."""
    res = _client().post(
        "/admin/attendance/manual-entry",
        json={
            "user_id": str(UID),
            "date": "2026-07-05",
            "check_in": "לא שעה",
            "check_out": None,
            "reason": "בדיקה",
        },
    )
    assert res.status_code == 422


def test_status_widget():
    res = _client().get("/admin/attendance/status")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert body["events_today"] == 7
    assert body["last_event_at"].startswith("2026-07-05T13:03")
