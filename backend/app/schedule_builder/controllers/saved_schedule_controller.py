"""
SavedScheduleController — save & download a week's frozen schedule snapshot.

Endpoints (all behind ``require_admin_role``; dependency rule B → A allowed):
- ``POST /admin/builder/weeks/{week_id}/save-schedule`` — snapshot the live board.
- ``GET  /admin/builder/saved-schedules``               — which weeks have one.
- ``GET  /admin/builder/export/saved-schedule/{week_id}`` — download as xlsx.

The download path contains ``/export/`` so the frontend ``request()`` blob-handling
applies unchanged.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.dependencies import get_excel_export_service, require_admin_role
from app.exceptions import AppBaseException
from app.schedule_builder.dependencies import get_saved_schedule_service
from app.schedule_builder.schemas.saved_schedule_schemas import SavedScheduleResponse
from app.schedule_builder.services.saved_schedule_service import (
    SavedScheduleService,
)
from app.services.excel_export_service import ExcelExportService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/builder",
    tags=["Admin – Builder – Saved Schedule"],
    dependencies=[Depends(require_admin_role)],
)


@router.post("/weeks/{week_id}/save-schedule", response_model=SavedScheduleResponse)
async def save_schedule(
    week_id: uuid.UUID,
    service: SavedScheduleService = Depends(get_saved_schedule_service),
):
    """Snapshot the current live board + assignments for the week (upsert)."""
    try:
        saved = await service.save(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return SavedScheduleResponse.from_orm(saved)


@router.get("/saved-schedules", response_model=list[SavedScheduleResponse])
async def list_saved_schedules(
    service: SavedScheduleService = Depends(get_saved_schedule_service),
):
    """Return metadata for every saved snapshot (for the Weeks-page buttons)."""
    rows = await service.list_all()
    return [SavedScheduleResponse.from_orm(s) for s in rows]


@router.get("/export/saved-schedule/{week_id}")
async def download_saved_schedule(
    week_id: uuid.UUID,
    service: SavedScheduleService = Depends(get_saved_schedule_service),
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """Download the week's saved snapshot as an Excel (.xlsx) file.

    Renders from the stored snapshot only — works even after the source profile
    was deleted.
    """
    saved = await service.get(week_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="אין סידור שמור לשבוע זה")
    data = export_service.render_saved_schedule(saved.snapshot)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=schedule_{week_id}.xlsx"
            )
        },
    )
