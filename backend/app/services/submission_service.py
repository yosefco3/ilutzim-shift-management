"""
SubmissionService — business logic for weekly constraint submissions.
"""

import logging
import uuid

from app.constants import WeekStatus
from app.exceptions import UserNotFoundException, WeekLockedException
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schemas.submission_schemas import (
    SubmissionCreate,
    SubmissionResponse,
    SubmissionStatusGrid,
    SubmissionWithName,
    MissingGuardInfo,
)

logger = logging.getLogger("ilutzim")


class SubmissionService:
    """Orchestrates weekly constraint submission flow."""

    def __init__(
        self,
        submission_repo: SubmissionRepository,
        user_repo: UserRepository,
        week_repo: ScheduleWeekRepository,
    ) -> None:
        self._submission_repo = submission_repo
        self._user_repo = user_repo
        self._week_repo = week_repo

    async def create_submission(
        self, data: SubmissionCreate, *, override_lock: bool = False
    ) -> SubmissionResponse:
        """
        Submit constraints for a specific week.

        Persists the full submission — days, shifts (with hours) and general
        notes — via ``upsert_submission`` (creates a new submission or replaces
        an existing one's days). Validates week is open unless override_lock=True.
        """
        # Validate user exists
        user = await self._user_repo.get_by_id(data.user_id)
        if user is None:
            raise UserNotFoundException()

        # Validate week is open
        week = await self._week_repo.get_by_id(data.week_id)
        if week is None:
            raise UserNotFoundException()

        # LOCKED is final — submissions can no longer be edited by anyone, not
        # even an admin via override_lock. LOCKED is reached only by the Sunday
        # rollover, which freezes both the board and constraint submission. While
        # the week is CLOSED (incl. after "publish") an admin can still edit.
        if week.status == WeekStatus.LOCKED:
            raise WeekLockedException(
                "השבוע נעול סופית — לא ניתן לערוך אילוצים."
            )

        # OPEN → guards (and admins) may submit. CLOSED → only an admin editing on
        # behalf of guards (override_lock); a guard without override is blocked.
        if week.status != WeekStatus.OPEN and not override_lock:
            raise WeekLockedException()

        # Map the validated input → upsert payload (days + shift windows + notes)
        upsert_data = {
            "general_notes": data.general_notes,
            "has_deviation": False,
            "daily_statuses": [
                {
                    "date": day.date,
                    "is_available": day.is_available,
                    "shift_windows": [
                        {
                            "shift_type": shift.shift_type,
                            "start_time": shift.start_time,
                            "end_time": shift.end_time,
                        }
                        for shift in day.shifts
                    ],
                }
                for day in data.days
            ],
        }

        saved = await self._submission_repo.upsert_submission(
            data.user_id, data.week_id, upsert_data
        )
        logger.info(f"Submission saved: user={data.user_id}, week={data.week_id}")
        return SubmissionResponse.model_validate(saved)

    async def get_submissions_for_week(
        self, week_id: uuid.UUID
    ) -> list[SubmissionResponse]:
        """Return all submissions for a given week."""
        submissions = await self._submission_repo.get_submissions_for_week(week_id)
        return [SubmissionResponse.model_validate(s) for s in submissions]

    async def get_submissions_for_user(
        self, user_id: uuid.UUID
    ) -> list[SubmissionResponse]:
        """Return all submissions made by a given user."""
        submissions = await self._submission_repo.get_by_user(user_id)
        return [SubmissionResponse.model_validate(s) for s in submissions]

    async def get_submission(
        self, user_id: uuid.UUID, week_id: uuid.UUID
    ) -> SubmissionResponse | None:
        """Return a single submission by user + week."""
        sub = await self._submission_repo.get_submission(user_id, week_id)
        if sub is None:
            return None
        return SubmissionResponse.model_validate(sub)

    async def set_violation_acknowledged(
        self, submission_id: uuid.UUID, acknowledged: bool
    ) -> SubmissionResponse | None:
        """Acknowledge (or un-acknowledge) a submission's rule violations.

        Returns the updated submission, or ``None`` if it doesn't exist.
        """
        sub = await self._submission_repo.set_violation_acknowledged(
            submission_id, acknowledged
        )
        if sub is None:
            return None
        logger.info(
            "Violation acknowledgement set: submission=%s acknowledged=%s",
            submission_id,
            acknowledged,
        )
        return SubmissionResponse.model_validate(sub)

    async def get_submission_counts(self) -> dict[uuid.UUID, int]:
        """Return ``{week_id: submission_count}`` for every week."""
        return await self._submission_repo.count_by_week()

    async def get_week_submissions_grid(self, week_id: uuid.UUID) -> list[SubmissionStatusGrid]:
        """Return submission status for all users (active and inactive) for a week.

        The ``is_active`` flag lets the admin UI show active guards by default
        and list inactive guards separately. Reminders still target only the
        active guards (see the notifications controller).
        """
        submissions = await self._submission_repo.get_submissions_for_week(week_id)
        users = await self._user_repo.get_all_users()

        sub_by_user = {s.user_id: s for s in submissions}

        result = []
        for user in users:
            sub = sub_by_user.get(user.id)
            result.append(
                SubmissionStatusGrid(
                    user_id=user.id,
                    full_name=user.full_name,
                    phone_number=user.phone_number or "",
                    submitted_at=sub.submitted_at if sub else None,
                    is_active=user.is_active,
                    has_telegram=bool(user.telegram_id),
                )
            )

        return result

    async def get_week_submissions_detailed(
        self, week_id: uuid.UUID
    ) -> dict:
        """
        Return full submission details for a week grouped by status.

        Returns:
            {
                "submitted": list[SubmissionWithName],  # guards who submitted
                "missing": list[MissingGuardInfo],       # guards who didn't submit
                "week_label": str,                        # week display label
            }
        """
        submissions = await self._submission_repo.get_submissions_for_week(week_id)
        # All users (active + inactive) so the admin UI can show submission
        # details for inactive guards too; the grid carries the is_active flag.
        users = await self._user_repo.get_all_users()
        week = await self._week_repo.get_by_id(week_id)

        sub_by_user = {s.user_id: s for s in submissions}
        user_by_id = {u.id: u for u in users}

        submitted = []
        missing = []

        for user in users:
            sub = sub_by_user.get(user.id)
            if sub and sub.daily_statuses:  # has actual submission with days
                submission_response = SubmissionResponse.model_validate(sub)
                submitted.append(
                    SubmissionWithName(
                        **submission_response.model_dump(),
                        full_name=user.full_name,
                    )
                )
            else:
                missing.append(
                    MissingGuardInfo(
                        user_id=str(user.id),
                        full_name=user.full_name,
                        phone_number=user.phone_number or "",
                    )
                )

        week_label = f"{week.start_date.strftime('%d/%m/%Y')} - {week.end_date.strftime('%d/%m/%Y')}"

        return {
            "submitted": submitted,
            "missing": missing,
            "week_label": week_label,
        }