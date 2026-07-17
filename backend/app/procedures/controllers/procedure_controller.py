"""
Procedure-quiz admin endpoints (סד"פ).

Registered in ``main.py`` only when ``PROCEDURES_ENABLED`` is on, so with the
flag off every path here returns 404. Admin-auth like the other admin routers.
Generation calls the Claude API (mocked in tests); publish fans out via the
synchronous ``ProcedurePublisher`` seam.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.dependencies import require_admin_role
from app.procedures.dependencies import (
    get_generation_service,
    get_procedure_service,
    get_question_repo,
    get_question_service,
    get_settings_service,
)
from app.procedures.repositories.procedure_repository import ProcedureRepository
from app.procedures.repositories.question_repository import QuizQuestionRepository
from app.procedures.schemas import (
    DocxUploadOut,
    GenerateOut,
    ProcedureCreate,
    ProcedureListItem,
    ProcedureOut,
    ProcedureUpdate,
    PublishOut,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
    ResultRow,
)
from app.procedures.services.docx_service import MAX_DOCX_BYTES, extract_text_from_docx
from app.procedures.services.procedure_service import ProcedureService
from app.procedures.services.question_generation_service import (
    QuestionGenerationService,
)
from app.procedures.services.question_service import QuizQuestionService
from app.services.settings_service import SettingsService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/procedures",
    tags=["Admin – Procedures"],
    dependencies=[Depends(require_admin_role)],
)


def _question_out(q) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        text=q.text,
        options=list(q.options),
        correct_index=q.correct_index,
        display_order=q.display_order,
        is_active=q.is_active,
        source=q.source.value,
        edited_at=q.edited_at,
    )


def _procedure_out(proc) -> ProcedureOut:
    return ProcedureOut(
        id=proc.id,
        title=proc.title,
        body_text=proc.body_text,
        source_filename=proc.source_filename,
        status=proc.status.value,
        created_at=proc.created_at,
        published_at=proc.published_at,
        is_default=proc.is_default,
        questions=[_question_out(q) for q in (proc.questions or [])],
    )


@router.get("/ping")
async def ping() -> dict[str, bool]:
    """Wiring check — proves the feature-flagged router is registered."""
    return {"enabled": True}


@router.post("", response_model=ProcedureOut, status_code=201)
async def create_procedure(
    body: ProcedureCreate,
    service: ProcedureService = Depends(get_procedure_service),
) -> ProcedureOut:
    """Create a draft procedure from pasted title + text."""
    proc = await service.create(
        title=body.title, body_text=body.body_text, source_filename=None
    )
    # Re-fetch with the questions relationship eager-loaded (same as the
    # update/archive handlers): serializing the freshly-created instance would
    # lazy-load `proc.questions`, which raises MissingGreenlet on an async
    # session.
    full = await service.get(proc.id)
    return _procedure_out(full)


@router.post("/upload", response_model=DocxUploadOut)
async def upload_docx(
    file: UploadFile = File(...),
    title: str = Form(default=""),
) -> DocxUploadOut:
    """Extract text from an uploaded .docx for admin review (does NOT save).

    Enforces a 10 MB cap; returns the extracted text so the admin can edit it
    before creating the procedure.
    """
    data = await file.read(MAX_DOCX_BYTES + 1)
    if len(data) > MAX_DOCX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"הקובץ חורג ממגבלת ה-{MAX_DOCX_BYTES // (1024 * 1024)} מ\"ב",
        )
    text = extract_text_from_docx(data)
    return DocxUploadOut(
        text=text,
        source_filename=file.filename or "upload.docx",
        char_count=len(text),
    )


@router.get("", response_model=list[ProcedureListItem])
async def list_procedures(
    service: ProcedureService = Depends(get_procedure_service),
) -> list[ProcedureListItem]:
    rows = await service.list_all()
    return [ProcedureListItem(**r) for r in rows]


@router.get("/{procedure_id}", response_model=ProcedureOut)
async def get_procedure(
    procedure_id: uuid.UUID,
    service: ProcedureService = Depends(get_procedure_service),
) -> ProcedureOut:
    proc = await service.get(procedure_id)
    return _procedure_out(proc)


@router.patch("/{procedure_id}", response_model=ProcedureOut)
async def update_procedure(
    procedure_id: uuid.UUID,
    body: ProcedureUpdate,
    service: ProcedureService = Depends(get_procedure_service),
) -> ProcedureOut:
    proc = await service.update(
        procedure_id, title=body.title, body_text=body.body_text
    )
    # refresh questions for the response
    full = await service.get(procedure_id)
    return _procedure_out(full)


@router.post("/{procedure_id}/archive", response_model=ProcedureOut)
async def archive_procedure(
    procedure_id: uuid.UUID,
    service: ProcedureService = Depends(get_procedure_service),
) -> ProcedureOut:
    proc = await service.archive(procedure_id)
    full = await service.get(procedure_id)
    return _procedure_out(full)


@router.post("/{procedure_id}/generate", response_model=GenerateOut)
async def generate_questions(
    procedure_id: uuid.UUID,
    service: ProcedureService = Depends(get_procedure_service),
    question_service: QuizQuestionService = Depends(get_question_service),
    gen_service: QuestionGenerationService = Depends(get_generation_service),
    settings: SettingsService = Depends(get_settings_service),
    question_repo: QuizQuestionRepository = Depends(get_question_repo),
) -> GenerateOut:
    """Generate (or regenerate) the AI question bank for a DRAFT procedure."""
    proc = await service.get(procedure_id)
    if proc.status.value != "draft":
        raise HTTPException(status_code=409, detail="ניתן לחדש שאלות לנוהל טיוטה בלבד")
    model = str(await settings.get_setting("procedure_ai_model") or "claude-opus-4-8")
    items = await gen_service.generate(proc.body_text, model)
    created, _deleted = await question_service.regenerate(procedure_id, items)
    total = await question_repo.count_all(procedure_id)
    return GenerateOut(
        generated=created, skipped=len(items) - created, total_questions=total
    )


# ── Question editing ─────────────────────────────────────────────────────────


@router.post("/{procedure_id}/questions", response_model=QuestionOut, status_code=201)
async def add_question(
    procedure_id: uuid.UUID,
    body: QuestionCreate,
    question_service: QuizQuestionService = Depends(get_question_service),
) -> QuestionOut:
    q = await question_service.add_manual(
        procedure_id,
        text=body.text,
        options=body.options,
        correct_index=body.correct_index,
    )
    return _question_out(q)


@router.patch(
    "/{procedure_id}/questions/{question_id}", response_model=QuestionOut
)
async def update_question(
    procedure_id: uuid.UUID,
    question_id: uuid.UUID,
    body: QuestionUpdate,
    question_service: QuizQuestionService = Depends(get_question_service),
) -> QuestionOut:
    q = await question_service.update(
        procedure_id,
        question_id,
        text=body.text,
        options=body.options,
        correct_index=body.correct_index,
        is_active=body.is_active,
    )
    return _question_out(q)


@router.delete("/{procedure_id}/questions/{question_id}", status_code=204)
async def delete_question(
    procedure_id: uuid.UUID,
    question_id: uuid.UUID,
    question_service: QuizQuestionService = Depends(get_question_service),
) -> None:
    await question_service.delete(procedure_id, question_id)


# ── Publish + results ────────────────────────────────────────────────────────


@router.post("/{procedure_id}/publish", response_model=PublishOut)
async def publish_procedure(
    procedure_id: uuid.UUID,
    rebroadcast: bool = Query(default=False),
    service: ProcedureService = Depends(get_procedure_service),
) -> PublishOut:
    summary = await service.publish(procedure_id, rebroadcast=rebroadcast)
    return PublishOut(**summary)


@router.get("/{procedure_id}/results", response_model=list[ResultRow])
async def procedure_results(
    procedure_id: uuid.UUID,
    service: ProcedureService = Depends(get_procedure_service),
) -> list[ResultRow]:
    rows = await service.results(procedure_id)
    return [ResultRow(**r) for r in rows]
