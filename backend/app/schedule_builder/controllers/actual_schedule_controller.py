"""
ActualScheduleController — the editable execution board (steps 05–06).

Endpoints (all behind ``require_admin_role``):
- ``GET    /admin/actual/{week_id}/board``       — the actual board (lazy-seeds).
- ``POST   /admin/actual/{week_id}/assignments`` — place a guard on a cell.
- ``PATCH  /admin/actual/assignments/{id}``      — set/clear a time segment.
- ``DELETE /admin/actual/assignments/{id}``      — remove an assignment.

Unlike the planning board there is **no time gate**: any started week — the
running one or a long-finished one — stays editable (retroactive payroll
fixes). A *future* week is rejected (409): until it starts, the planning board
is the only truth.
"""

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.dependencies import require_admin_role
from app.exceptions import AppBaseException
from app.schedule_builder.dependencies import get_actual_schedule_service
from app.schedule_builder.schemas.actual_schemas import (
    ActualAssignmentCreate,
    ActualAssignmentResponse,
    ActualBoardResponse,
    ActualPositionCreate,
    ActualPositionResponse,
    ActualPositionUpdate,
    ActualSegmentUpdate,
    ReinforcementCreate,
    ReinforcementResponse,
    SaveAsProfileRequest,
    SaveAsProfileResponse,
)
from app.schedule_builder.services.actual_schedule_service import (
    ActualScheduleService,
)

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/actual",
    tags=["Admin – Actual Schedule"],
    dependencies=[Depends(require_admin_role)],
)


def _board_payload(board: dict) -> dict:
    """Service board dict → response shape (assignments via the guard mapper)."""
    return {
        **board,
        "assignments": [
            ActualAssignmentResponse.from_orm_with_guard(a)
            for a in board["assignments"]
        ],
        "reinforcements": [
            ReinforcementResponse.from_card(c)
            for c in board.get("reinforcements", [])
        ],
    }


@router.get("/{week_id}/board", response_model=ActualBoardResponse)
async def get_actual_board(
    week_id: uuid.UUID,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """The actual board for a started week (seeded lazily on first read)."""
    try:
        return _board_payload(await service.get_board(week_id))
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/{week_id}/assignments",
    response_model=ActualAssignmentResponse,
    status_code=201,
)
async def create_actual_assignment(
    week_id: uuid.UUID,
    payload: ActualAssignmentCreate,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Place a guard on an actual cell (free editing, soft warnings only)."""
    try:
        # The week must have its copy (409s for a future week); the position
        # must belong to that copy — not to some other week's board.
        actual = await service.ensure_for_week(week_id)
        assignment = await service.assign(
            payload.actual_position_id,
            payload.day_index,
            payload.user_id,
            payload.segment_start,
            payload.segment_end,
            expected_schedule_id=actual.id,
        )
        return ActualAssignmentResponse.from_orm_with_guard(assignment)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch(
    "/assignments/{assignment_id}", response_model=ActualAssignmentResponse
)
async def update_actual_assignment_segment(
    assignment_id: uuid.UUID,
    payload: ActualSegmentUpdate,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Set or clear an actual assignment's time segment."""
    try:
        assignment = await service.update_segment(
            assignment_id, payload.segment_start, payload.segment_end
        )
        return ActualAssignmentResponse.from_orm_with_guard(assignment)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_actual_assignment(
    assignment_id: uuid.UUID,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Remove a guard from an actual cell."""
    try:
        await service.unassign(assignment_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Positions (steps 06) ─────────────────────────────────────────────────────


@router.post(
    "/{week_id}/positions",
    response_model=ActualPositionResponse,
    status_code=201,
)
async def create_actual_position(
    week_id: uuid.UUID,
    payload: ActualPositionCreate,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Add an ad-hoc position mid-week (the unforeseen-event story)."""
    try:
        return await service.add_position(
            week_id,
            name=payload.name,
            day_schedules=payload.day_schedules,
            required_attributes=payload.required_attributes,
            is_event=payload.is_event,
            event_required_count=payload.event_required_count,
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/positions/{position_id}", response_model=ActualPositionResponse)
async def update_actual_position(
    position_id: uuid.UUID,
    payload: ActualPositionUpdate,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Edit an actual position's name / hours / days / event-ness."""
    try:
        return await service.update_position(
            position_id,
            name=payload.name,
            day_schedules=payload.day_schedules,
            required_attributes=payload.required_attributes,
            is_event=payload.is_event,
            event_required_count=payload.event_required_count,
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/positions/{position_id}", status_code=204)
async def delete_actual_position(
    position_id: uuid.UUID,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Drop a position from the actual board (its assignments go with it)."""
    try:
        await service.remove_position(position_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Reinforcements (מתגברים — step 11) ───────────────────────────────────────


@router.post(
    "/{week_id}/reinforcements",
    response_model=ReinforcementResponse,
    status_code=201,
)
async def create_reinforcement(
    week_id: uuid.UUID,
    payload: ReinforcementCreate,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Add a one-off external reinforcement guard to this week's pool."""
    try:
        card = await service.add_reinforcement(
            week_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone_number=payload.phone_number,
            note=payload.note,
            supervisor_name=payload.supervisor_name,
        )
        return ReinforcementResponse.from_card(card)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/reinforcements/{card_id}", status_code=204)
async def delete_reinforcement(
    card_id: uuid.UUID,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Remove a reinforcement card (and its one-off guard + assignments)."""
    try:
        await service.remove_reinforcement(card_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/export/reinforcements")
async def export_reinforcements_report(
    start: date,
    end: date,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """The reinforcements report xlsx — names, work dates and hours for the
    requested period (the UI offers daily / weekly / monthly cuts)."""
    try:
        data = await service.export_reinforcements_report(start, end)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=reinforcements_{start}_{end}.xlsx"
            )
        },
    )


@router.post("/{week_id}/save-as-profile", response_model=SaveAsProfileResponse)
async def save_actual_as_profile(
    week_id: uuid.UUID,
    payload: SaveAsProfileRequest,
    service: ActualScheduleService = Depends(get_actual_schedule_service),
):
    """Promote this week's actual board to a new reusable activation profile."""
    try:
        return await service.save_as_profile(week_id, payload.name)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)