"""
ProfileController — admin endpoints for activation profiles (part B).

Lives under the part-B boundary; uses ``require_admin_role`` from part A
(dependency rule: B → A is allowed).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_admin_role
from app.exceptions import AppBaseException
from app.schedule_builder.dependencies import get_profile_service
from app.schedule_builder.schemas.profile_schemas import (
    ProfileCreate,
    ProfileDuplicate,
    ProfileResponse,
    ProfileUpdate,
)
from app.schedule_builder.services.profile_service import ProfileService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/builder/profiles",
    tags=["Admin – Builder – Profiles"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("", response_model=list[ProfileResponse])
async def list_profiles(
    service: ProfileService = Depends(get_profile_service),
):
    """List all activation profiles, ordered for display."""
    return await service.list_profiles()


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: ProfileCreate,
    service: ProfileService = Depends(get_profile_service),
):
    """Create a new activation profile."""
    return await service.create_profile(
        name=data.name, kind=data.kind, description=data.description
    )


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: uuid.UUID,
    service: ProfileService = Depends(get_profile_service),
):
    """Get a single activation profile by ID."""
    try:
        return await service.get_profile(profile_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: uuid.UUID,
    data: ProfileUpdate,
    service: ProfileService = Depends(get_profile_service),
):
    """Rename / update profile meta (name / kind / description)."""
    try:
        return await service.rename_profile(
            profile_id, name=data.name, kind=data.kind, description=data.description
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{profile_id}/default", response_model=ProfileResponse)
async def set_default_profile(
    profile_id: uuid.UUID,
    service: ProfileService = Depends(get_profile_service),
):
    """Mark a profile as the default (clears the flag on any other)."""
    try:
        return await service.set_default_profile(profile_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/{profile_id}/duplicate",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_profile(
    profile_id: uuid.UUID,
    data: ProfileDuplicate | None = None,
    service: ProfileService = Depends(get_profile_service),
):
    """Duplicate a profile (the core workflow). Optional new name."""
    try:
        return await service.duplicate_profile(
            profile_id, new_name=(data.new_name if data else None)
        )
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/{profile_id}/delete-impact")
async def profile_delete_impact(
    profile_id: uuid.UUID,
    service: ProfileService = Depends(get_profile_service),
):
    """Report how many weeks/assignments deleting this profile would wipe, so the
    UI can warn before the irreversible cascade."""
    try:
        return await service.delete_impact(profile_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: uuid.UUID,
    service: ProfileService = Depends(get_profile_service),
):
    """Delete a profile (blocked if it is the sole remaining profile)."""
    try:
        await service.delete_profile(profile_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
