"""
BoardController — admin endpoints for the read-only schedule board (part B).

Endpoints:
- ``GET  /admin/builder/board/next``             — board for the **next week**
  (the upcoming week guards submit availability for); no week id needed.
- ``GET  /admin/builder/weeks/{week_id}/profile`` — the effective profile.
- ``PUT  /admin/builder/weeks/{week_id}/profile`` — bind a profile to the week.
- ``GET  /admin/builder/weeks/{week_id}/board``   — the grid for a specific week.

Behind ``require_admin_role`` (dependency rule: B → A is allowed).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_admin_role
from app.exceptions import AppBaseException
from app.schedule_builder.dependencies import (
    get_board_service,
    get_week_profile_service,
)
from app.schedule_builder.schemas.board_schemas import (
    BoardResponse,
    WeekProfileAssign,
    WeekProfileResponse,
)
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.services.week_profile_service import WeekProfileService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/builder",
    tags=["Admin – Builder – Board"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("/board/next", response_model=BoardResponse)
async def get_next_week_board(
    service: BoardService = Depends(get_board_service),
):
    """Return the read-only board for the next week (the upcoming guard week)."""
    try:
        return await service.resolve_next_week_board()
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/weeks/{week_id}/profile", response_model=WeekProfileResponse)
async def get_week_profile(
    week_id: uuid.UUID,
    service: WeekProfileService = Depends(get_week_profile_service),
):
    """Return the profile a week is built from (explicit, or default fallback)."""
    try:
        profile, is_default_fallback = await service.get_effective_profile(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"profile": profile, "is_default_fallback": is_default_fallback}


@router.put("/weeks/{week_id}/profile", response_model=WeekProfileResponse)
async def set_week_profile(
    week_id: uuid.UUID,
    data: WeekProfileAssign,
    service: WeekProfileService = Depends(get_week_profile_service),
):
    """Bind ``profile_id`` to the week (replacing any existing binding)."""
    try:
        await service.set_profile(week_id, data.profile_id)
        profile, is_default_fallback = await service.get_effective_profile(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"profile": profile, "is_default_fallback": is_default_fallback}


@router.get("/weeks/{week_id}/board", response_model=BoardResponse)
async def get_board(
    week_id: uuid.UUID,
    service: BoardService = Depends(get_board_service),
):
    """Return the resolved positions × days grid for the week."""
    try:
        return await service.resolve_board(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
