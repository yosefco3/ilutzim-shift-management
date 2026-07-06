"""
SubmissionController — guard submission endpoints.
"""

import logging
import uuid
from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    get_current_user,
    get_settings_service,
    get_submission_service,
    get_user_service,
    get_week_service,
    require_admin_role,
)
from app.constants import ShiftType
from app.messages import Messages
from app.models.user import User
from app.schemas.submission_schemas import (
    AcknowledgeViolationRequest,
    AdminSubmissionRequest,
    GuardSubmissionRequest,
    ShiftWindowInput,
    DayStatusInput,
    SubmissionCreate,
    SubmissionResponse,
)
from app.schemas.week_schemas import WeekWithDaysResponse
from app.services.settings_service import SettingsService
from app.services.submission_service import SubmissionService
from app.services.user_service import UserService
from app.services.week_service import WeekService

logger = logging.getLogger("ilutzim")

router = APIRouter(prefix="/submissions", tags=["Submissions"])


@router.get("/current-week", response_model=WeekWithDaysResponse | None)
async def get_current_open_week(
    week_service: WeekService = Depends(get_week_service),
):
    """Get the week guards should see for the submission form.

    Returns the open week when one exists; otherwise the latest relevant week
    (closed/locked) **with its status**, so the UI can show a status
    banner instead of a generic "no week" error. Returns ``null`` only when no
    week exists at all. Submitting is still gated on the week being OPEN in the
    POST handler below.
    """
    return await week_service.get_relevant_week_with_days()


@router.get("/my", response_model=SubmissionResponse | None)
async def get_my_submission(
    week_id: uuid.UUID = Query(..., description="Week ID"),
    current_user: User = Depends(get_current_user),
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Get the authenticated guard's submission for a given week.

    Returns ``null`` if no submission exists yet.
    """
    return await submission_service.get_submission(current_user.id, week_id)


@router.post("", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_schedule(
    data: GuardSubmissionRequest,
    current_user: User = Depends(get_current_user),
    submission_service: SubmissionService = Depends(get_submission_service),
    week_service: WeekService = Depends(get_week_service),
):
    """Submit a guard's weekly schedule preferences.

    The week must be open for submissions.
    The guard is authenticated via Telegram WebApp init data.
    """
    # Guard: must have an open week
    open_week = await week_service.get_current_open_week()
    if open_week is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=Messages.SUBMISSION_CLOSED,
        )
    if str(open_week.id) != str(data.week_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=Messages.SUBMISSION_WRONG_WEEK,
        )

    # Convert GuardSubmissionRequest → SubmissionCreate
    try:
        submission_create = _convert_guard_request(data, open_week.start_date, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    try:
        submission = await submission_service.create_submission(submission_create)
    except Exception as e:
        logger.error(f"Submission failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Send Telegram success notification (non-critical — failure is logged but not returned)
    if current_user.telegram_id:
        try:
            from app.bot.notifications import notify_submission_success
            week_label = f"{open_week.start_date.strftime('%d/%m/%Y')} - {open_week.end_date.strftime('%d/%m/%Y')}"
            await notify_submission_success(int(current_user.telegram_id), week_label)
        except Exception as e:
            logger.warning(f"Failed to send submission success notification: {e}")

    return submission


@router.get(
    "/admin",
    response_model=SubmissionResponse | None,
    dependencies=[Depends(require_admin_role)],
)
async def admin_get_submission(
    user_id: uuid.UUID = Query(..., description="Guard user ID"),
    week_id: uuid.UUID = Query(..., description="Week ID"),
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Return a guard's existing submission for a week, for an admin to view and
    edit. **Admin only.** Returns ``null`` if the guard hasn't submitted yet.

    Works for any guard — including those who submitted via Telegram — so the
    admin can load and edit whatever constraints already exist.
    """
    return await submission_service.get_submission(user_id, week_id)


@router.post(
    "/admin",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_role)],
)
async def admin_submit_schedule(
    data: AdminSubmissionRequest,
    submission_service: SubmissionService = Depends(get_submission_service),
    week_service: WeekService = Depends(get_week_service),
    user_service: UserService = Depends(get_user_service),
):
    """Submit a guard's weekly schedule on the guard's behalf. **Admin only.**

    For guards without Telegram, an admin fills the constraints from the
    dashboard. Unlike the guard endpoint, this is allowed for a CLOSED week as
    well (``override_lock=True``) — including after "publish", which keeps the
    week CLOSED. The one exception is a **LOCKED** week (the Sunday rollover): it
    is final, so editing constraints is rejected for everyone, admin included.

    If the guard *does* have Telegram linked, they receive a notification that
    the admin filled their constraints on their behalf.
    """
    # Raises UserNotFoundException (404) via the global handler if missing.
    week = await week_service.get_week(data.week_id)

    try:
        submission_create = _convert_guard_request(data, week.start_date, data.user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    try:
        submission = await submission_service.create_submission(
            submission_create, override_lock=True
        )
    except Exception as e:
        logger.error(f"Admin submission failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Notify the guard (if they have Telegram) that the admin filled for them.
    # Non-critical — failure is logged but never fails the submission.
    guard = await user_service.get_user(data.user_id)
    if guard and guard.telegram_id:
        try:
            from app.bot.notifications import notify_admin_filled_constraints
            week_label = f"{week.start_date.strftime('%d/%m/%Y')} - {week.end_date.strftime('%d/%m/%Y')}"
            await notify_admin_filled_constraints(int(guard.telegram_id), week_label)
        except Exception as e:
            logger.warning(f"Failed to send admin-filled-constraints notification: {e}")

    return submission


@router.get("/shift-defaults")
async def get_shift_defaults(
    settings_service: SettingsService = Depends(get_settings_service),
):
    """Return the default shift hours (editable by admin via /admin/settings).

    Used by the guard submission form to pre-fill hours when a shift is toggled on.
    Public endpoint — no auth required.
    """
    keys = ("shift_default_morning", "shift_default_afternoon", "shift_default_night")
    result = {}
    for key in keys:
        raw = await settings_service.get_setting(key)
        parts = (raw or "").split("-")
        result[key] = {
            "from_hour": parts[0] if len(parts) >= 1 else "",
            "to_hour": parts[1] if len(parts) >= 2 else "",
        }
    return result


@router.get("/constraint-rules")
async def get_constraint_rules(
    settings_service: SettingsService = Depends(get_settings_service),
):
    """Constraint-rule thresholds (admin-editable via /admin/settings).

    Used by the guard submission form to show soft (non-blocking) warnings.
    Public endpoint — no auth required.
    """
    keys = ("min_shifts_per_guard", "min_nights", "min_evenings", "max_consecutive_days")
    result = {}
    for key in keys:
        raw = await settings_service.get_setting(key)
        try:
            result[key] = int(raw)
        except (TypeError, ValueError):
            result[key] = 0
    return result


@router.patch(
    "/{submission_id}/acknowledge-violation",
    response_model=SubmissionResponse,
    dependencies=[Depends(require_admin_role)],
)
async def acknowledge_violation(
    submission_id: uuid.UUID,
    data: AcknowledgeViolationRequest,
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Acknowledge (or un-acknowledge) a submission's rule violations. **Admin
    only.** Acknowledging hides the violation marker in the submissions grid."""
    updated = await submission_service.set_violation_acknowledged(
        submission_id, data.acknowledged
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    return updated


@router.get(
    "/week/{week_id}",
    response_model=list[SubmissionResponse],
    dependencies=[Depends(require_admin_role)],
)
async def get_submissions_for_week(
    week_id: uuid.UUID,
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Get all submissions for a specific week. **Admin only** — exposes every
    guard's availability for the week."""
    return await submission_service.get_submissions_for_week(week_id)


@router.get(
    "/user/{user_id}",
    response_model=list[SubmissionResponse],
    dependencies=[Depends(require_admin_role)],
)
async def get_submissions_for_user(
    user_id: uuid.UUID,
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Get all submissions for a specific user. **Admin only** — prevents IDOR
    enumeration of other guards' submissions."""
    return await submission_service.get_submissions_for_user(user_id)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_time(hour_str: str | None) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS' into a time object.  Defaults to 00:00."""
    if not hour_str or not hour_str.strip():
        return time(0, 0)
    parts = hour_str.strip().split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(Messages.VAL_BAD_TIME)
    return time(h, m)


_ANCHOR = time(7, 0)  # start of the security day (07:00 → 07:00)


def _validate_form_window(shift_type: ShiftType, start: time, end: time) -> None:
    """Enforce the security-day rules on a *form-submitted* shift window.

    The security day runs 07:00 → 07:00 the next morning, so:
    - no shift may start before 07:00, and
    - a night shift may end no later than 07:00 the next morning.

    Raises ``ValueError`` (mapped to 422 by the endpoints). This guards only the
    guard/admin submission forms — the constraints **import** ingests external
    data and is reconciled by the availability layer instead, so it is exempt.
    """
    if start < _ANCHOR:
        raise ValueError(Messages.VAL_SHIFT_BEFORE_ANCHOR)
    if shift_type == ShiftType.NIGHT:
        start_min = (start.hour * 60 + start.minute - 420) % 1440
        end_min = (end.hour * 60 + end.minute - 420) % 1440 or 1440  # 07:00 → 1440
        if end_min <= start_min:  # wraps past 07:00 next morning (or doesn't advance)
            raise ValueError(Messages.VAL_NIGHT_PAST_ANCHOR)
    elif start >= end:  # morning/evening must not cross midnight or be zero-length
        raise ValueError(Messages.VAL_SAME_START_END)


def _convert_guard_request(
    data: GuardSubmissionRequest,
    week_start: date,
    user_id: uuid.UUID,
) -> SubmissionCreate:
    """Convert a GuardSubmissionRequest to SubmissionCreate for the service layer."""
    days: list[DayStatusInput] = []
    for d in data.days:
        day_date = week_start + timedelta(days=d.day_index)
        shifts: list[ShiftWindowInput] = []
        for s in d.shifts:
            # Skip shifts with empty from_hour or to_hour (guard didn't fill hours)
            if not s.from_hour or not s.from_hour.strip():
                continue
            if not s.to_hour or not s.to_hour.strip():
                continue
            start_time = _parse_time(s.from_hour)
            end_time = _parse_time(s.to_hour)
            _validate_form_window(s.shift_type, start_time, end_time)
            shifts.append(
                ShiftWindowInput(
                    shift_type=s.shift_type,
                    start_time=start_time,
                    end_time=end_time,
                )
            )
        day_status = DayStatusInput(
            date=day_date,
            is_available=len(shifts) > 0,
            shifts=shifts,
        )
        days.append(day_status)

    return SubmissionCreate(
        week_id=data.week_id,
        user_id=user_id,
        general_notes=data.general_notes,
        days=days,
    )
