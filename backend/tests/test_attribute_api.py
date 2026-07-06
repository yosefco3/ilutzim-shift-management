"""
Tests for the requirement-attributes API (part B — schedule builder).

Controller-layer tests with an in-memory fake service and ``require_admin_role``
overridden to pass.
"""

import uuid
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import require_admin_role
from app.exceptions import (
    AttributeKeyConflictException,
    AttributeNotFoundException,
)
from app.schedule_builder.controllers.attribute_controller import router as attribute_router
from app.schedule_builder.dependencies import get_attribute_service
from app.schedule_builder.models.requirement_attribute import RequirementAttribute


class FakeAttributeService:
    def __init__(self):
        self._attrs: list[RequirementAttribute] = []

    def _make(self, key, label):
        a = RequirementAttribute(key=key, label=label, display_order=len(self._attrs))
        a.id = uuid.uuid4()
        a.created_at = datetime(2026, 1, 1)
        return a

    async def list_attributes(self):
        return self._attrs

    async def create_attribute(self, key, label):
        if any(a.key == key for a in self._attrs):
            raise AttributeKeyConflictException()
        a = self._make(key, label)
        self._attrs.append(a)
        return a

    def _find(self, aid):
        for a in self._attrs:
            if a.id == aid:
                return a
        raise AttributeNotFoundException()

    async def update_attribute(self, aid, key=None, label=None):
        a = self._find(aid)
        if key is not None:
            a.key = key
        if label is not None:
            a.label = label
        return a

    async def delete_attribute(self, aid):
        self._attrs.remove(self._find(aid))


def _make_client(service):
    app = FastAPI()
    app.include_router(attribute_router)
    app.dependency_overrides[get_attribute_service] = lambda: service
    app.dependency_overrides[require_admin_role] = lambda: None
    return TestClient(app)


class TestAttributeAPI:
    def test_create_then_list(self):
        svc = FakeAttributeService()
        client = _make_client(svc)
        resp = client.post("/admin/builder/attributes", json={"key": "armed", "label": "חמוש"})
        assert resp.status_code == 201
        assert resp.json()["key"] == "armed"

        resp = client.get("/admin/builder/attributes")
        assert [a["label"] for a in resp.json()] == ["חמוש"]

    def test_create_bad_key_422(self):
        client = _make_client(FakeAttributeService())
        resp = client.post("/admin/builder/attributes", json={"key": "Armed!", "label": "חמוש"})
        assert resp.status_code == 422

    def test_create_duplicate_key_409(self):
        svc = FakeAttributeService()
        client = _make_client(svc)
        client.post("/admin/builder/attributes", json={"key": "armed", "label": "חמוש"})
        resp = client.post("/admin/builder/attributes", json={"key": "armed", "label": "אחר"})
        assert resp.status_code == 409

    def test_patch_updates(self):
        svc = FakeAttributeService()
        a = svc._make("armed", "חמוש")
        svc._attrs.append(a)
        client = _make_client(svc)
        resp = client.patch(f"/admin/builder/attributes/{a.id}", json={"label": "נושא נשק"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "נושא נשק"

    def test_patch_empty_422(self):
        svc = FakeAttributeService()
        a = svc._make("armed", "חמוש")
        svc._attrs.append(a)
        client = _make_client(svc)
        resp = client.patch(f"/admin/builder/attributes/{a.id}", json={})
        assert resp.status_code == 422

    def test_delete_ok(self):
        svc = FakeAttributeService()
        a = svc._make("armed", "חמוש")
        svc._attrs.append(a)
        client = _make_client(svc)
        resp = client.delete(f"/admin/builder/attributes/{a.id}")
        assert resp.status_code == 204


class TestAttributeAPIAuth:
    def test_requires_admin(self):
        app = FastAPI()
        app.include_router(attribute_router)
        app.dependency_overrides[get_attribute_service] = lambda: FakeAttributeService()
        client = TestClient(app)
        resp = client.get("/admin/builder/attributes")
        assert resp.status_code in (401, 403)
