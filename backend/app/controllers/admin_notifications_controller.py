"""
AdminNotificationsController — admin endpoints for sending notifications.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    get_user_service,
    get_week_service,
    get_submission_service,
    require_admin_role,
)
from app.services.user_service import UserService
from app.services.week_service import WeekService
from app.services.submission_service import SubmissionService

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/notifications",
    tags=["Admin – Notifications"],
    dependencies=[Depends(require_admin_role)],
)


@router.post("/remind/{week_id}")
async def send_submission_reminder(
    week_id: uuid.UUID,
    week_service: WeekService = Depends(get_week_service),
    user_service: UserService = Depends(get_user_service),
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Send a reminder to guards who haven't submitted yet for a given week."""
    # Raises a not-found exception if the week doesn't exist.
    week = await week_service.get_week(week_id)

    users = await user_service.get_all_active_users()

    # Collect active guards who haven't submitted yet, keeping their name so the
    # reminder can greet each one personally. Track separately those we cannot
    # remind because they have no (or an invalid) Telegram link — otherwise the
    # UI would wrongly report "everyone submitted" when in fact someone is just
    # unreachable.
    recipients: list[dict] = []
    missing_count = 0
    skipped_no_telegram = 0
    for user in users:
        submission = await submission_service.get_submission(user.id, week_id)
        if submission is not None:
            continue
        missing_count += 1
        if not user.telegram_id:
            skipped_no_telegram += 1
            continue
        try:
            telegram_id = int(user.telegram_id)
        except (TypeError, ValueError):
            logger.warning("Skipping invalid telegram_id for user %s", user.id)
            skipped_no_telegram += 1
            continue
        name = (getattr(user, "full_name", None)
                or f"{user.first_name} {user.last_name}").strip()
        recipients.append({"telegram_id": telegram_id, "name": name})

    # Send via bot
    sent_count = 0
    if recipients:
        try:
            from app.bot.notifications import notify_closing_reminder

            sent_count = await notify_closing_reminder(
                week_start=week.start_date,
                week_end=getattr(week, "end_date", None),
                deadline_text="בקרוב",
                recipients=recipients,
            )
        except Exception as exc:
            logger.error("Failed to send reminders: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bot service unavailable",
            ) from exc

    return {
        "message": "Reminder notifications sent",
        "week_id": str(week_id),
        "total_active": len(users),
        "missing": missing_count,
        "skipped_no_telegram": skipped_no_telegram,
        "reminded": sent_count,
    }
