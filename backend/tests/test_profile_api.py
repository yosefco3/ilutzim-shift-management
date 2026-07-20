"""
Tests for the activation-profiles API (part B — schedule builder).

Controller-layer tests: a FastAPI app with the profile router, an in-memory
fake service (the real service+DB is covered in test_profile_service.py), and
``require_admin_role`` overridden to pass.
"""

import uuid
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import require_admin_role
from app.exceptions import ProfileDeleteBlockedException, ProfileNotFoundException
from app.schedule_builder.controllers.profile_controller import router as profile_router
from app.schedule_builder.dependencies import get_profile_service
from app.schedule_builder.models.activation_profile import ActivationProfile


class FakeProfileService:
    """In-memory stand-in for ProfileService."""

    def __init__(self):
        self._profiles: list[ActivationProfile] = []

    def _make(self, name, kind=None, description=None, is_default=False, day_labels=None):
        p = ActivationProfile(
            name=name, kind=kind, description=description,
            is_default=is_default, display_order=len(self._profiles),
            day_labels=day_labels if day_labels is not None else {},
        )
        p.id = uuid.uuid4()
        p.created_at = datetime(2026, 1, 1)
        return p

    def seed(self, name="שגרה", is_default=True):
        p = self._make(name, kind=name, is_default=is_default)
        self._profiles.append(p)
        return p

    async def list_profiles(self):
        return self._profiles

    async def create_profile(self, name, kind=None, description=None):
        p = self._make(name, kind, description)
        self._profiles.append(p)
        return p

    def _find(self, pid):
        for p in self._profiles:
            if p.id == pid:
                return p
        raise ProfileNotFoundException()

    async def get_profile(self, pid):
        return self._find(pid)

    async def rename_profile(self, pid, name=None, kind=None, description=None, day_labels=None):
        p = self._find(pid)
        if name is not None:
            p.name = name
        if kind is not None:
            p.kind = kind
        if description is not None:
            p.description = description
        if day_labels is not None:
            p.day_labels = day_labels
        return p

    async def duplicate_profile(self, pid, new_name=None):
        src = self._find(pid)
        dup = self._make(
            new_name or f"{src.name} (עותק)", src.kind, src.description,
            day_labels=dict(src.day_labels or {}),
        )
        self._profiles.append(dup)
        return dup

    async def delete_impact(self, pid):
        self._find(pid)  # raises ProfileNotFoundException for unknown ids
        return {"weeks": 2, "assignments": 5, "is_last": len(self._profiles) <= 1}

    async def delete_profile(self, pid):
        p = self._find(pid)
        if len(self._profiles) <= 1:
            raise ProfileDeleteBlockedException()
        self._profiles.remove(p)


def _make_client(service: FakeProfileService) -> TestClient:
    app = FastAPI()
    app.include_router(profile_router)
    app.dependency_overrides[get_profile_service] = lambda: service
    app.dependency_overrides[require_admin_role] = lambda: None
    return TestClient(app)


class TestProfileAPI:
    def test_create_then_list(self):
        svc = FakeProfileService()
        client = _make_client(svc)

        resp = client.post("/admin/builder/profiles", json={"name": "חג", "kind": "חג"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "חג"
        assert body["kind"] == "חג"
        assert body["is_default"] is False

        resp = client.get("/admin/builder/profiles")
        assert resp.status_code == 200
        assert [p["name"] for p in resp.json()] == ["חג"]

    def test_patch_renames(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        client = _make_client(svc)

        resp = client.patch(
            f"/admin/builder/profiles/{p.id}", json={"name": "שגרה מעודכנת"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "שגרה מעודכנת"

    def test_patch_empty_body_422(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        client = _make_client(svc)
        resp = client.patch(f"/admin/builder/profiles/{p.id}", json={})
        assert resp.status_code == 422

    def test_duplicate(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        client = _make_client(svc)

        resp = client.post(f"/admin/builder/profiles/{p.id}/duplicate", json={})
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "שגרה (עותק)"
        assert body["is_default"] is False

    def test_get_missing_404(self):
        svc = FakeProfileService()
        client = _make_client(svc)
        resp = client.get(f"/admin/builder/profiles/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_ok(self):
        svc = FakeProfileService()
        svc.seed("שגרה")
        target = svc._make("חג")
        svc._profiles.append(target)
        client = _make_client(svc)

        resp = client.delete(f"/admin/builder/profiles/{target.id}")
        assert resp.status_code == 204

    def test_delete_last_blocked_409(self):
        svc = FakeProfileService()
        only = svc.seed("שגרה")
        client = _make_client(svc)
        resp = client.delete(f"/admin/builder/profiles/{only.id}")
        assert resp.status_code == 409

    def test_delete_impact_reports_counts(self):
        svc = FakeProfileService()
        svc.seed("שגרה")
        target = svc._make("חג")
        svc._profiles.append(target)
        client = _make_client(svc)

        resp = client.get(f"/admin/builder/profiles/{target.id}/delete-impact")
        assert resp.status_code == 200
        assert resp.json() == {"weeks": 2, "assignments": 5, "is_last": False}

    def test_delete_impact_unknown_404(self):
        svc = FakeProfileService()
        svc.seed("שגרה")
        client = _make_client(svc)
        resp = client.get(f"/admin/builder/profiles/{uuid.uuid4()}/delete-impact")
        assert resp.status_code == 404


class TestProfileDayLabels:
    """day_labels on PATCH/duplicate — validation lives on ProfileUpdate ([EDGE D4])."""

    def test_patch_sets_day_labels(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        client = _make_client(svc)

        resp = client.patch(
            f"/admin/builder/profiles/{p.id}",
            json={"day_labels": {"4": "ט׳ באב"}},
        )
        assert resp.status_code == 200
        assert resp.json()["day_labels"] == {"4": "ט׳ באב"}
        # Passed through to the service and stored on the profile.
        assert svc._find(p.id).day_labels == {"4": "ט׳ באב"}

    def test_patch_invalid_day_key_422(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        client = _make_client(svc)
        for bad in ("7", "x"):
            resp = client.patch(
                f"/admin/builder/profiles/{p.id}",
                json={"day_labels": {bad: "label"}},
            )
            assert resp.status_code == 422, bad

    def test_patch_value_too_long_422(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        client = _make_client(svc)
        resp = client.patch(
            f"/admin/builder/profiles/{p.id}",
            json={"day_labels": {"1": "א" * 51}},
        )
        assert resp.status_code == 422

    def test_patch_whitespace_value_dropped(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        client = _make_client(svc)
        resp = client.patch(
            f"/admin/builder/profiles/{p.id}",
            json={"day_labels": {"4": "ט׳ באב", "5": "   "}},
        )
        assert resp.status_code == 200
        # The blank-only entry is dropped, not stored as an empty string.
        assert resp.json()["day_labels"] == {"4": "ט׳ באב"}

    def test_patch_empty_dict_clears_labels(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        p.day_labels = {"4": "ט׳ באב"}
        client = _make_client(svc)
        resp = client.patch(
            f"/admin/builder/profiles/{p.id}", json={"day_labels": {}}
        )
        assert resp.status_code == 200
        assert resp.json()["day_labels"] == {}

    def test_patch_without_field_leaves_labels(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        p.day_labels = {"4": "ט׳ באב"}
        client = _make_client(svc)
        resp = client.patch(
            f"/admin/builder/profiles/{p.id}", json={"name": "שגרה חדשה"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "שגרה חדשה"
        # day_labels absent from the body = unchanged.
        assert body["day_labels"] == {"4": "ט׳ באב"}

    def test_duplicate_copies_day_labels(self):
        svc = FakeProfileService()
        p = svc.seed("שגרה")
        p.day_labels = {"4": "ט׳ באב"}
        client = _make_client(svc)
        resp = client.post(f"/admin/builder/profiles/{p.id}/duplicate", json={})
        assert resp.status_code == 201
        assert resp.json()["day_labels"] == {"4": "ט׳ באב"}


class TestProfileAPIAuth:
    def test_requires_admin(self):
        # No override of require_admin_role -> real guard rejects unauthenticated.
        svc = FakeProfileService()
        app = FastAPI()
        app.include_router(profile_router)
        app.dependency_overrides[get_profile_service] = lambda: svc
        client = TestClient(app)
        resp = client.get("/admin/builder/profiles")
        assert resp.status_code in (401, 403)
