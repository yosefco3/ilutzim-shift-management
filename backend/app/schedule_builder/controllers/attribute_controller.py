"""
AttributeController — admin endpoints for the requirement-attribute vocabulary
(part B). Behind ``require_admin_role`` (dependency rule: B → A is allowed).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_admin_role
from app.exceptions import AppBaseException
from app.schedule_builder.dependencies import get_attribute_service
from app.schedule_builder.schemas.attribute_schemas import (
    AttributeCreate,
    AttributeResponse,
    AttributeUpdate,
)
from app.schedule_builder.services.attribute_service import AttributeService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/builder/attributes",
    tags=["Admin – Builder – Attributes"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("", response_model=list[AttributeResponse])
async def list_attributes(
    service: AttributeService = Depends(get_attribute_service),
):
    """List all requirement attributes, ordered for display."""
    return await service.list_attributes()


@router.post("", response_model=AttributeResponse, status_code=status.HTTP_201_CREATED)
async def create_attribute(
    data: AttributeCreate,
    service: AttributeService = Depends(get_attribute_service),
):
    """Create a new requirement attribute."""
    try:
        return await service.create_attribute(key=data.key, label=data.label)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/{attribute_id}", response_model=AttributeResponse)
async def update_attribute(
    attribute_id: uuid.UUID,
    data: AttributeUpdate,
    service: AttributeService = Depends(get_attribute_service),
):
    """Update a requirement attribute (key / label)."""
    try:
        return await service.update_attribute(
            attribute_id, key=data.key, label=data.label
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attribute(
    attribute_id: uuid.UUID,
    service: AttributeService = Depends(get_attribute_service),
):
    """Delete a requirement attribute."""
    try:
        await service.delete_attribute(attribute_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
