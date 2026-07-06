"""
AdminWeeksController — admin endpoints for schedule week management.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.constants import WeekStatus
from app.dependencies import get_submission_service, get_week_service, require_admin_role
from app.exceptions import AppBaseException
from app.schemas.submission_schemas import SubmissionStatusGrid, WeekSubmissionsDetailed
from app.schemas.week_schemas import (
    PublishPreviewItem,
    PublishResult,
    WeekCreate,
    WeekResponse,
    WeekStatusUpdate,
)
from app.services.submission_service import SubmissionService
from app.services.week_service import WeekService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/weeks",
    tags=["Admin – Weeks"],
    dependencies=[Depends(require_admin_role)],
)


@router.get("", response_model=list[WeekResponse])
async def list_weeks(
    week_service: WeekService = Depends(get_week_service),
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """List all schedule weeks, each annotated with its submission count."""
    weeks = await week_service.get_all_weeks()
    counts = await submission_service.get_submission_counts()
    for w in weeks:
        w.submission_count = counts.get(w.id, 0)
    return weeks


@router.post("", response_model=WeekResponse, status_code=status.HTTP_201_CREATED)
async def create_week(
    data: WeekCreate,
    week_service: WeekService = Depends(get_week_service),
):
    """Create a new schedule week."""
    try:
        return await week_service.create_week(data)
    except Exception as e:
        logger.error(f"Week creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{week_id}", response_model=WeekResponse)
async def get_week(
    week_id: uuid.UUID,
    week_service: WeekService = Depends(get_week_service),
):
    """Get a specific week by ID."""
    try:
        return await week_service.get_week(week_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Week not found",
        )


@router.post("/{week_id}/open", response_model=WeekResponse)
async def reopen_week(
    week_id: uuid.UUID,
    week_service: WeekService = Depends(get_week_service),
):
    """Re-open a closed or locked week for submissions."""
    try:
        return await week_service.change_week_status(week_id, WeekStatus.OPEN)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as e:
        logger.error(f"Week reopen failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{week_id}/publish", response_model=PublishResult)
async def publish_week(
    week_id: uuid.UUID,
    week_service: WeekService = Depends(get_week_service),
):
    """Publish (or re-publish) a week: broadcast each guard their personal
    schedule + the schedule-grid PNG. Publishing keeps the week CLOSED (it never
    locks) and stamps ``published_at`` — the admin can keep editing and publish
    again until the week starts. Only the Sunday rollover locks a week.
    """
    try:
        return await week_service.publish_week(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as e:
        logger.error(f"Week publish failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{week_id}/publish-preview", response_model=list[PublishPreviewItem])
async def preview_publish_week(
    week_id: uuid.UUID,
    week_service: WeekService = Depends(get_week_service),
):
    """Preview the publish broadcast: return the personal-schedule message each
    guard *would* receive, without sending anything. Lets the admin verify content
    and recipients (e.g. while phone numbers / telegram ids are placeholder data).
    """
    try:
        return await week_service.preview_publish(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as e:
        logger.error(f"Week publish-preview failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch("/{week_id}/status", response_model=WeekResponse)
async def update_week_status(
    week_id: uuid.UUID,
    body: WeekStatusUpdate,
    week_service: WeekService = Depends(get_week_service),
):
    """Change a week's status (closed ⇄ open, either → locked; locked is final)."""
    try:
        return await week_service.change_week_status(week_id, body.status)
    except Exception as e:
        logger.error(f"Week status change failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{week_id}/submissions", response_model=list[SubmissionStatusGrid])
async def get_week_submissions(
    week_id: uuid.UUID,
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Get submission status for all users for a given week."""
    return await submission_service.get_week_submissions_grid(week_id)


@router.get("/{week_id}/submissions/detailed", response_model=WeekSubmissionsDetailed)
async def get_week_submissions_detailed(
    week_id: uuid.UUID,
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Get detailed submissions (with shifts) for a week, split by submitted/missing."""
    return await submission_service.get_week_submissions_detailed(week_id)


@router.delete("/{week_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_week(
    week_id: uuid.UUID,
    week_service: WeekService = Depends(get_week_service),
):
    """Delete a non-locked schedule week."""
    try:
        await week_service.delete_week(week_id)
    except AppBaseException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as e:
        logger.error(f"Week deletion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
