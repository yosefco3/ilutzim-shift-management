"""ConstraintsImportController — upload guard-constraints xlsx and import it.

Step 03 exposes a dry-run **preview** (parse + union-merge, no DB write).
Step 04 adds the **commit** that writes into the existing availability model.

All routes require admin auth and live under ``/admin/import/constraints``.
"""

import io
import logging
import uuid
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.dependencies import (
    get_constraints_commit_service,
    get_user_service,
    require_admin_role,
)
from app.schemas.constraints_import import (
    ConstraintsCommitResponse,
    ConstraintsPreviewResponse,
)
from app.services.constraints_import.commit import (
    ConstraintsCommitService,
    WeekNotFoundError,
)
from app.services.constraints_import.parser import parse_constraints_xlsx
from app.services.constraints_import.preview import build_preview
from app.services.user_service import UserService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/import/constraints",
    tags=["Admin – Constraints Import"],
    dependencies=[Depends(require_admin_role)],
)

_XLSX_SUFFIX = ".xlsx"
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024         # 5MB — קובץ אילוצים אמיתי < 1MB
_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # xlsx הוא zip; חוסם zip-bomb
_READ_CHUNK = 64 * 1024


async def _read_xlsx(file: UploadFile) -> bytes:
    """Validate and read an uploaded xlsx, raising a friendly 400 on bad input.

    Caps the streamed byte size (413) and the uncompressed zip size (413) so a
    zip-bomb cannot exhaust memory on the single Railway process before openpyxl
    even loads the workbook.
    """
    name = file.filename or ""
    if not name.lower().endswith(_XLSX_SUFFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="יש להעלות קובץ אקסל בפורמט .xlsx",
        )
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="הקובץ גדול מדי (מקסימום 5MB)",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="הקובץ ריק",
        )

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if sum(i.file_size for i in zf.infolist()) > _MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="הקובץ גדול מדי לאחר פריסה",
                )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="יש להעלות קובץ אקסל בפורמט .xlsx",
        )
    return data


async def _existing_names(user_service: UserService) -> set[str]:
    users = await user_service.get_all_users()
    return {u.full_name for u in users if getattr(u, "full_name", None)}


async def _existing_ids(user_service: UserService) -> set[str]:
    users = await user_service.get_all_users()
    return {str(u.id) for u in users if getattr(u, "id", None)}


@router.post("/preview", response_model=ConstraintsPreviewResponse)
async def preview_constraints(
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service),
):
    """Parse an uploaded constraints xlsx and return a clean preview (no write)."""
    data = await _read_xlsx(file)
    try:
        parsed = parse_constraints_xlsx(data)
    except Exception as exc:  # malformed workbook → 400, never 500
        logger.warning("constraints preview parse failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="לא ניתן לקרוא את קובץ האקסל — ודא שהוא תקין ובפורמט הצפוי",
        )

    existing = await _existing_names(user_service)
    existing_ids = await _existing_ids(user_service)
    return build_preview(parsed, existing, existing_ids)


@router.post("/commit", response_model=ConstraintsCommitResponse)
async def commit_constraints(
    file: UploadFile = File(...),
    week_id: uuid.UUID | None = Query(
        None, description="Override target week; defaults to the file's week range"
    ),
    commit_service: ConstraintsCommitService = Depends(get_constraints_commit_service),
):
    """Parse an uploaded constraints xlsx and persist it to the availability model."""
    data = await _read_xlsx(file)
    try:
        parsed = parse_constraints_xlsx(data)
    except Exception as exc:  # malformed workbook → 400, never 500
        logger.warning("constraints commit parse failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="לא ניתן לקרוא את קובץ האקסל — ודא שהוא תקין ובפורמט הצפוי",
        )

    try:
        return await commit_service.commit(parsed, week_id=week_id)
    except WeekNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
