"""
Guard WebApp view endpoint + read receipts + the results read column.

Service-level coverage (real in-memory session): the guard view returns both
bodies + the passed flag, records a first-open receipt for the calling guard
only, is idempotent on re-open, 404s for non-PUBLISHED/unknown, and feeds the
results ``read``/``first_read_at`` fields. Plus HTTP smoke tests for the route
wiring (200 with the response shape) and the 401 auth path.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.exceptions import UserNotFoundException
from app.models.user import User
from app.procedures.constants import AttemptStatus, ProcedureStatus
from app.procedures.controllers.procedure_controller import guard_router
from app.procedures.dependencies import get_procedure_service
from app.procedures.models import Procedure, QuizAttempt
from app.procedures.repositories import (
    ProcedureReadReceiptRepository,
    ProcedureRepository,
    QuizAttemptRepository,
    QuizQuestionRepository,
)
from app.procedures.services.procedure_service import ProcedureService
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.services.settings_service import SettingsService


class _FakePublisher:
    async def broadcast(self, recipients, title, procedure_id):
        return {"sent": 0, "skipped": 0, "total": 0}


def _svc(db_session) -> ProcedureService:
    return ProcedureService(
        ProcedureRepository(db_session),
        QuizQuestionRepository(db_session),
        QuizAttemptRepository(db_session),
        UserRepository(db_session),
        SettingsService(SystemSettingsRepository(db_session)),
        _FakePublisher(),
        ProcedureReadReceiptRepository(db_session),
    )


async def _published_proc(
    db_session, *, body_html="<p>HTML</p>", body_text="תוכן"
) -> Procedure:
    proc = Procedure(
        title="נהל קריאה",
        body_text=body_text,
        body_html=body_html,
        status=ProcedureStatus.PUBLISHED,
    )
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    return proc


async def _guard(db_session, telegram_id="111") -> User:
    user = User(
        phone_number=f"050{telegram_id[-7:]}",
        first_name="ג", last_name="ב", roles=[], telegram_id=telegram_id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── guard_view: shape + receipt ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guard_view_returns_bodies_and_passed_false(db_session):
    proc = await _published_proc(db_session)
    guard = await _guard(db_session)
    view = await _svc(db_session).guard_view(proc.id, guard)
    assert view["title"] == "נהל קריאה"
    assert view["body_html"] == "<p>HTML</p>"
    assert view["body_text"] == "תוכן"
    assert view["passed"] is False
    assert view["is_default"] is False


@pytest.mark.asyncio
async def test_guard_view_passed_true_when_attempt_passed(db_session):
    proc = await _published_proc(db_session)
    guard = await _guard(db_session)
    db_session.add(QuizAttempt(
        procedure_id=proc.id, user_id=guard.id, question_ids=[], answers={},
        started_at=datetime.now(timezone.utc), total_count=7, correct_count=7,
        passed=True, status=AttemptStatus.FINISHED,
    ))
    await db_session.commit()
    view = await _svc(db_session).guard_view(proc.id, guard)
    assert view["passed"] is True


@pytest.mark.asyncio
async def test_guard_view_records_receipt_for_calling_user_only(db_session):
    proc = await _published_proc(db_session)
    reader = await _guard(db_session, "111")
    other = await _guard(db_session, "222")
    await _svc(db_session).guard_view(proc.id, reader)
    read_map = await ProcedureReadReceiptRepository(db_session).read_map(proc.id)
    assert reader.id in read_map
    assert other.id not in read_map  # never opened → no receipt


@pytest.mark.asyncio
async def test_guard_view_second_open_is_idempotent_one_row(db_session):
    """Re-open never duplicates a row nor overwrites the original timestamp. [EDGE C1]"""
    proc = await _published_proc(db_session)
    guard = await _guard(db_session)
    svc = _svc(db_session)
    await svc.guard_view(proc.id, guard)
    first = await ProcedureReadReceiptRepository(db_session).read_map(proc.id)
    first_ts = first[guard.id]
    # second open
    await svc.guard_view(proc.id, guard)
    second = await ProcedureReadReceiptRepository(db_session).read_map(proc.id)
    assert len(second) == 1  # still exactly one row
    assert second[guard.id] == first_ts  # timestamp unchanged


# ── guard_view: visibility (PUBLISHED only) ──────────────────────────────────


@pytest.mark.asyncio
async def test_guard_view_draft_is_404(db_session):
    proc = Procedure(title="טיוטה", body_text="x", status=ProcedureStatus.DRAFT)
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    guard = await _guard(db_session)
    with pytest.raises(UserNotFoundException):
        await _svc(db_session).guard_view(proc.id, guard)


@pytest.mark.asyncio
async def test_guard_view_archived_is_404(db_session):
    proc = Procedure(title="ישן", body_text="x", status=ProcedureStatus.ARCHIVED)
    db_session.add(proc)
    await db_session.commit()
    await db_session.refresh(proc)
    guard = await _guard(db_session)
    with pytest.raises(UserNotFoundException):
        await _svc(db_session).guard_view(proc.id, guard)


@pytest.mark.asyncio
async def test_guard_view_unknown_id_is_404(db_session):
    guard = await _guard(db_session)
    with pytest.raises(UserNotFoundException):
        await _svc(db_session).guard_view(uuid.uuid4(), guard)


# ── results: read column ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_results_mark_read_for_guard_with_receipt(db_session):
    proc = await _published_proc(db_session)
    reader = await _guard(db_session, "111")
    stranger = await _guard(db_session, "222")
    # reader opens the page → receipt
    await _svc(db_session).guard_view(proc.id, reader)
    rows = {r["user_id"]: r for r in await _svc(db_session).results(proc.id)}
    assert rows[reader.id]["read"] is True
    assert rows[reader.id]["first_read_at"] is not None
    assert rows[stranger.id]["read"] is False
    assert rows[stranger.id]["first_read_at"] is None


# ── HTTP smoke (route wiring + auth) ─────────────────────────────────────────


def _guard_app():
    app = FastAPI()
    app.include_router(guard_router)
    return app


def test_guard_get_http_returns_guard_procedure_out():
    """The route is wired, the auth override works, and the response shape
    matches GuardProcedureOut (the controller forwards the service dict). The
    receipt/visibility logic itself is covered by the service-level tests above."""

    class _StubService:
        async def guard_view(self, procedure_id, user):
            return {
                "id": procedure_id,
                "title": "נהל",
                "body_html": "<p>HTML</p>",
                "body_text": "תוכן",
                "is_default": True,
                "passed": True,
            }

    guard = type("U", (), {"id": uuid.uuid4()})()
    app = _guard_app()
    app.dependency_overrides[get_current_user] = lambda: guard
    app.dependency_overrides[get_procedure_service] = lambda: _StubService()
    client = TestClient(app)
    resp = client.get(
        f"/procedures/{uuid.uuid4()}",
        headers={"X-Telegram-Init-Data": "__DEV_MODE__"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "נהל"
    assert body["body_html"] == "<p>HTML</p>"
    assert body["body_text"] == "תוכן"
    assert body["is_default"] is True
    assert body["passed"] is True
    app.dependency_overrides.clear()


def test_guard_get_http_401_without_valid_init_data():
    """No/invalid initData → 401 via the real get_current_user dependency. [EDGE A1]"""
    app = _guard_app()
    client = TestClient(app)
    resp = client.get(f"/procedures/{uuid.uuid4()}")
    assert resp.status_code == 401


def test_guard_get_http_401_invalid_init_data_blob():
    """A bogus (non-__DEV_MODE__) initData → 401 (signature check fails)."""
    app = _guard_app()
    client = TestClient(app)
    resp = client.get(
        f"/procedures/{uuid.uuid4()}",
        headers={"X-Telegram-Init-Data": "bogus-not-telegram-data"},
    )
    assert resp.status_code == 401
