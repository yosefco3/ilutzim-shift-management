"""
PositionController — admin endpoints for positions (part B).

Positions are nested under a profile for list/create (the screen is "within a
selected profile"); get/patch/delete operate on a position id. Behind
``require_admin_role`` (dependency rule: B → A is allowed).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_admin_role
from app.exceptions import AppBaseException
from app.schedule_builder.dependencies import get_position_service
from app.schedule_builder.schemas.position_schemas import (
    PositionCopy,
    PositionCreate,
    PositionReorder,
    PositionResponse,
    PositionUpdate,
)
from app.schedule_builder.services.position_service import PositionService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/builder",
    tags=["Admin – Builder – Positions"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("/profiles/{profile_id}/positions", response_model=list[PositionResponse])
async def list_positions(
    profile_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
):
    """List a profile's positions, ordered for display."""
    return await service.list_positions(profile_id)


@router.post(
    "/profiles/{profile_id}/positions",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_position(
    profile_id: uuid.UUID,
    data: PositionCreate,
    service: PositionService = Depends(get_position_service),
):
    """Create a position under a profile."""
    return await service.create_position(
        profile_id=profile_id,
        name=data.name,
        day_schedules=data.day_schedules,
        required_attributes=data.required_attributes,
        is_event=data.is_event,
        event_required_count=data.event_required_count,
    )


@router.put(
    "/profiles/{profile_id}/positions/order",
    response_model=list[PositionResponse],
)
async def reorder_positions(
    profile_id: uuid.UUID,
    data: PositionReorder,
    service: PositionService = Depends(get_position_service),
):
    """Persist a new position order within a profile (drag-and-drop on the board).

    The body must be an exact permutation of the profile's positions.
    """
    try:
        return await service.reorder_positions(profile_id, data.position_ids)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/positions/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
):
    """Get a single position by ID."""
    try:
        return await service.get_position(position_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/positions/{position_id}", response_model=PositionResponse)
async def update_position(
    position_id: uuid.UUID,
    data: PositionUpdate,
    service: PositionService = Depends(get_position_service),
):
    """Update a position (name / hours / requirements)."""
    try:
        return await service.update_position(
            position_id,
            name=data.name,
            day_schedules=data.day_schedules,
            required_attributes=data.required_attributes,
            is_event=data.is_event,
            event_required_count=data.event_required_count,
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/positions/{position_id}/copy",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def copy_position(
    position_id: uuid.UUID,
    data: PositionCopy,
    service: PositionService = Depends(get_position_service),
):
    """Deep-copy a position into another profile (drag-and-drop in the UI)."""
    try:
        return await service.copy_position(position_id, data.target_profile_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
):
    """Delete a position."""
    try:
        await service.delete_position(position_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
