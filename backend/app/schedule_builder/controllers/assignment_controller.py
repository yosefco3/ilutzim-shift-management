"""
AssignmentController — manual schedule assignment endpoints (part B, task 05).

Endpoints (all behind ``require_admin_role``; dependency rule B → A allowed):
- ``GET    /admin/builder/weeks/{week_id}/pool``        — assignable guards.
- ``GET    /admin/builder/weeks/{week_id}/assignments`` — cell assignments.
- ``POST   /admin/builder/weeks/{week_id}/assignments`` — place a guard on a cell.
- ``DELETE /admin/builder/assignments/{assignment_id}`` — remove an assignment.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_admin_role
from app.exceptions import AppBaseException, AssignmentNotFoundException
from app.schedule_builder.dependencies import (
    get_assignment_service,
    get_availability_service,
    get_board_service,
)
from app.schedule_builder.schemas.assignment_schemas import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentSegmentUpdate,
    PoolGuardSchema,
)
from app.schedule_builder.services.assignment_service import AssignmentService
from app.schedule_builder.services.availability_service import AvailabilityService
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.services.warnings_service import compute_board_warnings

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/builder",
    tags=["Admin – Builder – Assignments"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("/weeks/{week_id}/pool", response_model=list[PoolGuardSchema])
async def get_pool(
    week_id: uuid.UUID,
    service: AvailabilityService = Depends(get_availability_service),
):
    """Return the enriched pool: guards who submitted, with availability + hours."""
    try:
        return await service.build_pool(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/weeks/{week_id}/warnings")
async def get_warnings(
    week_id: uuid.UUID,
    board_service: BoardService = Depends(get_board_service),
    availability_service: AvailabilityService = Depends(get_availability_service),
    assignment_service: AssignmentService = Depends(get_assignment_service),
):
    """The canonical soft-warning report for a built week.

    Runs the same engine (``warnings_service.compute_board_warnings``) the auto-fill
    algorithm uses, so the admin and the algorithm see identical warnings. Returns
    ``{by_cell, by_guard, summary}``.
    """
    try:
        board = await board_service.resolve_board(week_id)
        pool = await availability_service.build_pool(week_id)
        assignments = await assignment_service.list_for_week(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    assignments_by_cell: dict[str, list] = {}
    for a in assignments:
        key = f"{a.position_id}:{a.day_index}"
        assignments_by_cell.setdefault(key, []).append({
            "user_id": a.user_id,
            "user_full_name": a.user.full_name,
            "user_roles": list(a.user.roles or []),
            "segment_start": a.segment_start,
            "segment_end": a.segment_end,
        })
    return compute_board_warnings(board, assignments_by_cell, pool)


@router.get("/weeks/{week_id}/assignments", response_model=list[AssignmentResponse])
async def list_assignments(
    week_id: uuid.UUID,
    service: AssignmentService = Depends(get_assignment_service),
):
    """Return every assignment for the week (to overlay on the board)."""
    try:
        rows = await service.list_for_week(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return [AssignmentResponse.from_orm_with_guard(a) for a in rows]


@router.post("/weeks/{week_id}/assignments", response_model=AssignmentResponse)
async def create_assignment(
    week_id: uuid.UUID,
    data: AssignmentCreate,
    service: AssignmentService = Depends(get_assignment_service),
):
    """Place a guard on a cell (week × position × day)."""
    try:
        a = await service.assign(
            week_id,
            data.position_id,
            data.day_index,
            data.user_id,
            data.segment_start,
            data.segment_end,
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return AssignmentResponse.from_orm_with_guard(a)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment_segment(
    assignment_id: uuid.UUID,
    data: AssignmentSegmentUpdate,
    service: AssignmentService = Depends(get_assignment_service),
):
    """Set/clear an assignment's time segment (the draggable-divider save)."""
    try:
        a = await service.update_segment(
            assignment_id, data.segment_start, data.segment_end
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return AssignmentResponse.from_orm_with_guard(a)


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: uuid.UUID,
    service: AssignmentService = Depends(get_assignment_service),
):
    """Remove an assignment by id."""
    deleted = await service.unassign(assignment_id)
    if not deleted:
        exc = AssignmentNotFoundException()
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
