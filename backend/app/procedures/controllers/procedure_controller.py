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
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, require_admin_role
from app.procedures.constants import ProcedureStatus
from app.procedures.dependencies import (
    build_quiz_service,
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
    GuardProcedureOut,
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
from app.procedures.services.docx_service import (
    MAX_DOCX_BYTES,
    extract_html_from_docx,
    extract_text_from_docx,
)
from app.procedures.services.procedure_service import ProcedureService
from app.procedures.services.question_generation_service import (
    QuestionGenerationService,
)
from app.procedures.services.question_service import QuizQuestionService
from app.services.settings_service import SettingsService
from app.database import get_pool
from app.exceptions import ValidationException

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/procedures",
    tags=["Admin – Procedures"],
    dependencies=[Depends(require_admin_role)],
)


# Guard-facing router (סד"פ WebApp reading page). Same PROCEDURES_ENABLED gate
# at registration (main.py) — with the flag off every path here 404s. Auth is the
# guard initData dependency (incl. the __DEV_MODE__ dev bypass). [EDGE A1–A3, B2]
guard_router = APIRouter(
    prefix="/procedures",
    tags=["Guard – Procedures"],
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
        body_html=proc.body_html,
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
    """Create a draft procedure from pasted title + text (+ optional body_html)."""
    proc = await service.create(
        title=body.title,
        body_text=body.body_text,
        body_html=body.body_html,
        source_filename=None,
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
    before creating the procedure. Also returns the sanitized rich-HTML snapshot
    (``body_html``) for the guard WebApp reading page — None when conversion is
    impossible/empty, so the page falls back to ``body_text``. Text extraction
    remains the validity gate, so a failed/empty HTML conversion never breaks
    the upload.
    """
    data = await file.read(MAX_DOCX_BYTES + 1)
    if len(data) > MAX_DOCX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"הקובץ חורג ממגבלת ה-{MAX_DOCX_BYTES // (1024 * 1024)} מ\"ב",
        )
    text = extract_text_from_docx(data)
    # Best-effort: a failed/empty HTML snapshot leaves body_html=None (fallback).
    body_html = extract_html_from_docx(data)
    return DocxUploadOut(
        text=text,
        body_html=body_html,
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
        procedure_id,
        title=body.title,
        body_text=body.body_text,
        body_html=body.body_html,
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


@router.delete("/{procedure_id}", status_code=204)
async def delete_procedure(
    procedure_id: uuid.UUID,
    service: ProcedureService = Depends(get_procedure_service),
) -> None:
    """Hard-delete a procedure + all its quiz history (archive keeps history)."""
    await service.delete(procedure_id)


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
    bank_size = await settings.get_setting("procedure_bank_size")
    items = await gen_service.generate(proc.body_text, model, bank_size=bank_size)
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


# ── Guard WebApp (reading page) ─────────────────────────────────────────────


@guard_router.get("/{procedure_id}", response_model=GuardProcedureOut)
async def guard_get_procedure(
    procedure_id: uuid.UUID,
    user=Depends(get_current_user),
    service: ProcedureService = Depends(get_procedure_service),
) -> GuardProcedureOut:
    """Return one PUBLISHED procedure for the guard reading page.

    PUBLISHED only (DRAFT/ARCHIVED/unknown → 404). Records the first-open read
    receipt best-effort. [EDGE A1–A3, C1, D1]
    """
    view = await service.guard_view(procedure_id, user)
    return GuardProcedureOut(**view)


@guard_router.post("/{procedure_id}/quiz/start")
async def guard_start_quiz(
    procedure_id: uuid.UUID,
    user=Depends(get_current_user),
    session=Depends(get_pool),
):
    """Start the quiz from the WebApp reading page.

    Opens a sampled attempt (superseding any stale one — a double-tap is safe,
    [EDGE C2]) and sends the first question to the guard's Telegram chat as a
    quiz poll, then the page closes itself. PUBLISHED only → 404; an empty
    active-question bank → 409; the bot unavailable / send failed → 503 (the
    attempt is still persisted, so a later retry safely supersedes it).
    [EDGE D1, I1]
    """
    procedure_repo = ProcedureRepository(session)
    proc = await procedure_repo.get_by_id(procedure_id)
    if proc is None or proc.status != ProcedureStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="הנוהל אינו זמין יותר")
    if not await QuizQuestionRepository(session).list_active(procedure_id):
        raise HTTPException(
            status_code=409, detail="אין שאלות זמינות למבחן כרגע"
        )

    try:
        telegram_id = int(user.telegram_id)
    except (TypeError, ValueError):
        # No resolvable chat id → cannot deliver a poll.
        raise HTTPException(
            status_code=503,
            detail="הבוט אינו זמין כרגע — נסה שוב מאוחר יותר",
        )

    quiz_service = build_quiz_service(session)
    try:
        # Lazy import: the controllers package must not import the bot at load
        # (layering — procedures may import part A; nothing imports back).
        from app.bot.quiz_sender import start_and_send

        outcome = await start_and_send(
            telegram_id, user.id, procedure_id, quiz_service
        )
    except ValidationException as exc:
        # Either a race (bank emptied / status changed between the pre-checks
        # and the start) or the one-quiz-at-a-time gate — surface the service's
        # own Hebrew message so the page shows WHY the start was refused.
        raise HTTPException(status_code=409, detail=exc.message)

    # Persist the attempt even if the poll send failed — a retry supersedes it
    # (matches the bot callback's commit-on-failure behavior, so the two paths
    # cannot drift). [EDGE I1]
    await session.commit()
    if not outcome.sent:
        # A 503 (not a raised 503) so the attempt commit above is not rolled
        # back by the get_pool error path.
        return JSONResponse(
            status_code=503,
            content={"detail": "הבוט אינו זמין כרגע — נסה שוב מאוחר יותר"},
        )
    return {"started": True}
