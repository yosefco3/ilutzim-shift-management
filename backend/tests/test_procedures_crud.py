"""
Procedure CRUD service + docx extraction + the upload endpoint (incl. 10 MB cap).
"""

from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.exceptions import ConflictException, ValidationException
from app.procedures.constants import ProcedureStatus
from app.procedures.controllers.procedure_controller import router as procedures_router
from app.procedures.repositories import (
    ProcedureRepository,
    QuizAttemptRepository,
    QuizQuestionRepository,
)
from app.procedures.services.docx_service import extract_text_from_docx
from app.procedures.services.procedure_service import ProcedureService
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.services.settings_service import SettingsService


class _FakePublisher:
    def __init__(self):
        self.calls = []

    async def broadcast(self, recipients, title, body_text, procedure_id):
        self.calls.append((list(recipients), title, procedure_id))
        return {"sent": len(recipients), "skipped": 0, "total": len(recipients)}


def _svc(db_session, publisher=None) -> ProcedureService:
    return ProcedureService(
        ProcedureRepository(db_session),
        QuizQuestionRepository(db_session),
        QuizAttemptRepository(db_session),
        UserRepository(db_session),
        SettingsService(SystemSettingsRepository(db_session)),
        publisher or _FakePublisher(),
    )


def _docx_bytes(paragraphs):
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── CRUD service ────────────────────────────────────────────────────────────


async def test_create_is_draft(db_session):
    svc = _svc(db_session)
    proc = await svc.create("נהל אבטחה", "תוכן הנהל", source_filename="a.docx")
    assert proc.status == ProcedureStatus.DRAFT
    assert proc.source_filename == "a.docx"


async def test_list_all_includes_question_counts(db_session):
    svc = _svc(db_session)
    proc = await svc.create("נהל", "תוכן")
    from app.procedures.constants import QuestionSource
    from app.procedures.models import QuizQuestion

    db_session.add(
        QuizQuestion(
            procedure_id=proc.id, text="q1", options=["a", "b"],
            correct_index=0, display_order=0, source=QuestionSource.AI,
        )
    )
    db_session.add(
        QuizQuestion(
            procedure_id=proc.id, text="q2", options=["a", "b"],
            correct_index=0, display_order=1, is_active=False, source=QuestionSource.AI,
        )
    )
    await db_session.commit()
    rows = await svc.list_all()
    assert rows[0]["active_questions"] == 1
    assert rows[0]["total_questions"] == 2


async def test_get_with_questions_and_404(db_session):
    svc = _svc(db_session)
    proc = await svc.create("נהל", "תוכן")
    got = await svc.get(proc.id)
    assert got.questions == []
    import uuid

    with pytest.raises(Exception):
        await svc.get(uuid.uuid4())


async def test_update_only_while_draft(db_session):
    svc = _svc(db_session)
    proc = await svc.create("נהל", "תוכן")
    updated = await svc.update(proc.id, title="נהל חדש", body_text=None)
    assert updated.title == "נהל חדש"
    # Force-publish to test the guard.
    proc = await svc._procedures.get_by_id(proc.id)
    await svc._procedures.update(proc.id, status=ProcedureStatus.PUBLISHED)
    with pytest.raises(ConflictException):
        await svc.update(proc.id, title="אסור", body_text=None)


async def test_archive_sets_archived(db_session):
    svc = _svc(db_session)
    proc = await svc.create("נהל", "תוכן")
    archived = await svc.archive(proc.id)
    assert archived.status == ProcedureStatus.ARCHIVED
    # idempotent
    again = await svc.archive(proc.id)
    assert again.status == ProcedureStatus.ARCHIVED


# ── docx extraction ─────────────────────────────────────────────────────────


def test_extract_text_from_valid_docx():
    data = _docx_bytes(["סעיף אחד", "סעיף שני"])
    text = extract_text_from_docx(data)
    assert "סעיף אחד" in text
    assert "סעיף שני" in text
    assert "\n\n" in text


def test_extract_text_invalid_docx_raises_validation():
    with pytest.raises(ValidationException):
        extract_text_from_docx(b"not a real docx file content")


def test_extract_text_includes_tables():
    from docx import Document

    doc = Document()
    doc.add_paragraph("הקדמה")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "עמדה"
    table.rows[0].cells[1].text = "שעה"
    buf = BytesIO()
    doc.save(buf)
    text = extract_text_from_docx(buf.getvalue())
    assert "הקדמה" in text
    assert "עמדה" in text
    assert "שעה" in text


# ── Upload endpoint (10 MB cap + happy path) ─────────────────────────────────


def _client():
    from app.dependencies import require_admin_role

    app = FastAPI()
    app.include_router(procedures_router)
    app.dependency_overrides[require_admin_role] = lambda: None
    return TestClient(app)


def test_upload_docx_returns_extracted_text():
    data = _docx_bytes(["נהל כניסה לאתר"])
    client = _client()
    res = client.post(
        "/admin/procedures/upload",
        files={"file": ("proc.docx", data, "application/vnd.openxmlformats")},
        data={"title": "נהל"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "נהל כניסה לאתר" in body["text"]
    assert body["source_filename"] == "proc.docx"
    assert body["char_count"] == len(body["text"])


def test_upload_docx_10mb_cap(monkeypatch):
    """A file over the cap is rejected (413) before extraction."""
    from app.procedures.controllers import procedure_controller as ctrl

    monkeypatch.setattr(ctrl, "MAX_DOCX_BYTES", 64)
    data = _docx_bytes(["x" * 200])  # bigger than the patched 64-byte cap
    client = _client()
    res = client.post(
        "/admin/procedures/upload",
        files={"file": ("big.docx", data, "application/vnd.openxmlformats")},
        data={"title": "נהל"},
    )
    assert res.status_code == 413


@pytest.mark.asyncio
async def test_create_endpoint_serializes_fresh_procedure(db_session):
    """Regression: the create endpoint must not lazy-load `questions` off the
    freshly-created instance (MissingGreenlet on an async session) — it re-fetches
    with the relationship eager-loaded before serializing."""
    from app.procedures.controllers.procedure_controller import create_procedure
    from app.procedures.schemas import ProcedureCreate

    out = await create_procedure(
        ProcedureCreate(title="נוהל חדש", body_text="תוכן הנוהל"),
        service=_svc(db_session),
    )
    assert out.title == "נוהל חדש"
    assert out.status == "draft"
    assert out.questions == []
