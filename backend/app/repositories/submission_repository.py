"""
Submission repository — data access for weekly submissions with eager loading.
"""

import uuid
from datetime import date, time

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import ShiftType, SubmissionStatus
from app.models.weekly_submission import WeeklySubmission
from app.models.daily_status import DailyStatus
from app.models.shift_window import ShiftWindow
from app.repositories.base_repository import BaseRepository
from app.logging_config import get_logger

logger = get_logger(__name__)


class SubmissionRepository(BaseRepository[WeeklySubmission]):
    """Data-access operations for WeeklySubmission entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WeeklySubmission)

    def _eager_load_query(self):
        """Base query with eager loading of daily_statuses -> shift_windows."""
        return select(self.model_class).options(
            selectinload(WeeklySubmission.daily_statuses).selectinload(
                DailyStatus.shift_windows
            )
        )

    async def get_submission(
        self, user_id: uuid.UUID, week_id: uuid.UUID
    ) -> WeeklySubmission | None:
        """Get a submission by user+week with eager-loaded relations."""
        stmt = self._eager_load_query().where(
            WeeklySubmission.user_id == user_id,
            WeeklySubmission.week_id == week_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_submission(
        self, user_id: uuid.UUID, week_id: uuid.UUID, data: dict
    ) -> WeeklySubmission:
        """Create or replace a submission with its daily_statuses and shift_windows.

        data format:
        {
            "general_notes": str | None,
            "has_deviation": bool,
            "daily_statuses": [
                {
                    "date": date,
                    "is_available": bool,
                    "shift_windows": [
                        {"shift_type": ShiftType, "start_time": time, "end_time": time}
                    ]
                },
                ...
            ]
        }
        """
        existing = await self.get_submission(user_id, week_id)

        if existing is not None:
            # Delete old daily_statuses (cascade will remove shift_windows)
            for ds in existing.daily_statuses:
                await self.session.delete(ds)
            await self.session.flush()

            # Update submission-level fields
            existing.general_notes = data.get("general_notes")
            existing.has_deviation = data.get("has_deviation", False)
            submission = existing
        else:
            # Create new submission
            submission = WeeklySubmission(
                user_id=user_id,
                week_id=week_id,
                general_notes=data.get("general_notes"),
                has_deviation=data.get("has_deviation", False),
            )
            self.session.add(submission)
            await self.session.flush()

        # Create new daily_statuses and shift_windows
        for ds_data in data.get("daily_statuses", []):
            daily_status = DailyStatus(
                submission_id=submission.id,
                date=ds_data["date"],
                is_available=ds_data["is_available"],
            )
            self.session.add(daily_status)
            await self.session.flush()

            for sw_data in ds_data.get("shift_windows", []):
                shift_window = ShiftWindow(
                    daily_status_id=daily_status.id,
                    shift_type=sw_data["shift_type"],
                    start_time=sw_data["start_time"],
                    end_time=sw_data["end_time"],
                )
                self.session.add(shift_window)

        await self.session.flush()

        # Capture ID before expiring to avoid lazy-load in async context
        submission_id = submission.id

        # Expire cached relations so the eager reload fetches fresh data
        self.session.expire(submission)

        # Reload with eager-loaded relations
        stmt = self._eager_load_query().where(WeeklySubmission.id == submission_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def set_violation_acknowledged(
        self, submission_id: uuid.UUID, acknowledged: bool
    ) -> WeeklySubmission | None:
        """Set the violation_acknowledged flag and return the eager-loaded row.

        Returns ``None`` if no submission matches the given id.
        """
        stmt = self._eager_load_query().where(WeeklySubmission.id == submission_id)
        result = await self.session.execute(stmt)
        submission = result.scalar_one_or_none()
        if submission is None:
            return None
        submission.violation_acknowledged = acknowledged
        await self.session.flush()
        return submission

    async def get_submissions_for_week(
        self, week_id: uuid.UUID
    ) -> list[WeeklySubmission]:
        """Get all submissions for a week, eagerly loaded."""
        stmt = self._eager_load_query().where(WeeklySubmission.week_id == week_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user(
        self, user_id: uuid.UUID
    ) -> list[WeeklySubmission]:
        """Get all submissions made by a user, eagerly loaded."""
        stmt = self._eager_load_query().where(
            WeeklySubmission.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_missing_submissions(
        self, week_id: uuid.UUID, active_user_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        """Return user IDs that have NOT submitted for the given week."""
        if not active_user_ids:
            return []

        stmt = select(WeeklySubmission.user_id).where(
            WeeklySubmission.week_id == week_id,
            WeeklySubmission.user_id.in_(active_user_ids),
        )
        result = await self.session.execute(stmt)
        submitted_ids = set(result.scalars().all())
        return [uid for uid in active_user_ids if uid not in submitted_ids]

    async def count_by_week(self) -> dict[uuid.UUID, int]:
        """Return ``{week_id: submission_count}`` for every week in one query."""
        stmt = select(
            WeeklySubmission.week_id, func.count(WeeklySubmission.id)
        ).group_by(WeeklySubmission.week_id)
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_submission_stats(self, week_id: uuid.UUID) -> dict:
        """Return aggregate counts for a week's submissions."""
        stmt = select(WeeklySubmission).where(WeeklySubmission.week_id == week_id)
        result = await self.session.execute(stmt)
        submissions = list(result.scalars().all())

        submitted = 0
        variance = 0
        pending = 0
        auto_absence = 0

        for sub in submissions:
            # Determine status based on has_deviation flag
            if sub.has_deviation:
                variance += 1
            else:
                submitted += 1

        return {
            "submitted": submitted,
            "pending": pending,
            "variance": variance,
            "auto_absence": auto_absence,
            "total": len(submissions),
        }