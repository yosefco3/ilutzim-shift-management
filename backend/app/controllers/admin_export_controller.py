"""
AdminExportController — admin endpoints for Excel export.

Three export types:
1. Weekly schedule grid  – /admin/export/week/{week_id}
2. Deviation report      – /admin/export/deviation/{week_id}
3. Guard history         – /admin/export/guard/{user_id}
"""

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_excel_export_service, require_admin_role
from app.exceptions import AppBaseException
from app.services.excel_export_service import ExcelExportService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/export",
    tags=["Admin – Export"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("/week/{week_id}")
async def export_week_excel(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export a week's schedule as an Excel (.xlsx) file.

    Returns a grid with guards as rows and days as columns,
    showing shift selections, events, and auto-absence.
    """
    try:
        data = await export_service.export_weekly_schedule(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=schedule_{week_id}.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Excel weekly export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/constraints/{week_id}")
async def export_constraints_excel(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export all submitted constraints for a week as an Excel (.xlsx) file.

    One row per guard who submitted, showing per-day availability,
    the exact shift windows chosen, and their general notes.
    """
    try:
        data = await export_service.export_constraints_report(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=constraints_{week_id}.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Excel constraints export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/schedule/{week_id}")
async def export_schedule_excel(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export the *built* schedule as an Excel (.xlsx) file.

    Rows = positions (in board order), columns = days (Sun–Sat); each cell shows
    the assigned guard(s) and their hours. A tiled cell splits the position block
    into one sub-row per guard.
    """
    try:
        data = await export_service.export_schedule_grid(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=schedule_{week_id}.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Excel schedule export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/actual-schedule/{week_id}")
async def export_actual_schedule_excel(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export the ACTUAL schedule (סידור בפועל) as an Excel (.xlsx) file.

    Same grid layout as the planned-schedule export, read from the week's
    editable execution copy — "what really happened". Only meaningful for a
    week that already started; a future week is rejected (its truth is still
    the planning board / saved snapshot).
    """
    try:
        data = await export_service.export_actual_schedule_grid(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=actual_schedule_{week_id}.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except AppBaseException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Actual-schedule excel export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/actual-schedule-png/{week_id}")
async def export_actual_schedule_png(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export the ACTUAL schedule (סידור בפועל) as a PNG image — the same grid
    renderer as the planned PNG, read from the week's execution copy.
    """
    try:
        data = await export_service.export_actual_schedule_grid_png(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="image/png",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=actual_schedule_{week_id}.png"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except AppBaseException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Actual-schedule PNG export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/schedule-png/{week_id}")
async def export_schedule_png(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export the *built* schedule as a PNG image — the same grid (colours/layout)
    as the Excel export, rendered with Pillow. This is exactly what guards receive
    on publish, so the admin can preview it before broadcasting.
    """
    try:
        data = await export_service.export_schedule_grid_png(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="image/png",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=schedule_{week_id}.png"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Schedule PNG export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/guard-positions/{week_id}")
async def export_guard_positions_excel(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export a per-guard "positions" overview as an Excel (.xlsx) file.

    One block per active guard, columns = days (Sun–Sat); each cell shows the
    guard's position and hours that day. Guards with no shifts are listed too.
    """
    try:
        data = await export_service.export_guard_positions(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=guard_positions_{week_id}.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Excel guard-positions export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/deviation/{week_id}")
async def export_deviation_excel(
    week_id: uuid.UUID,
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export a deviation report for a specific week.

    Lists guards whose shift counts fall below the minimum threshold.
    """
    try:
        data = await export_service.export_deviation_report(week_id)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=deviation_{week_id}.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Excel deviation export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/guard/{user_id}")
async def export_guard_history_excel(
    user_id: uuid.UUID,
    start_date: date = Query(..., description="Start date of the range"),
    end_date: date = Query(..., description="End date of the range"),
    export_service: ExcelExportService = Depends(get_excel_export_service),
):
    """
    Export a single guard's history report as Excel.

    Shows submission status and events for each week in the date range.
    """
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be >= start_date",
        )
    try:
        data = await export_service.export_guard_history(
            user_id, start_date, end_date
        )
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=guard_history_{user_id}.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Excel guard history export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )