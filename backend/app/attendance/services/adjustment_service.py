"""
AdjustmentService — the admin's single free-editing tool (stage 3 / 02).

Every operation appends an audit row (never mutates one), touches the raw log
only by APPENDING manual events, and finishes with a targeted pairing
recompute so the derived shifts and the comparison stay in step. Reasons are
mandatory — the single-admin model's "approval" is this trail.
"""

import logging
import uuid
from datetime import date as date_type, datetime

from app.attendance.constants import (
    AdjustmentAction,
    PunchDirection,
    PunchSource,
)
from app.attendance.models.attendance_adjustment import AttendanceAdjustment
from app.attendance.repositories.adjustment_repository import (
    AttendanceAdjustmentRepository,
)
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.services.pairing_service import PairingService
from app.exceptions import ValidationException

logger = logging.getLogger("ilutzim")


class AdjustmentService:
    """Admin corrections: edit / add / void punches, approve an absence."""

    def __init__(
        self,
        events: AttendanceEventRepository,
        adjustments: AttendanceAdjustmentRepository,
        pairing: PairingService,
    ) -> None:
        self._events = events
        self._adjustments = adjustments
        self._pairing = pairing

    @staticmethod
    def _require_reason(reason: str) -> str:
        cleaned = (reason or "").strip()
        if len(cleaned) < 2:
            raise ValidationException("נדרשת סיבה לתיקון")
        return cleaned

    async def edit_time(
        self,
        event_id: uuid.UUID,
        new_time: datetime,
        reason: str,
        *,
        now: datetime,
    ) -> AttendanceAdjustment:
        """Replace a punch's timestamp: void the original, append a MANUAL
        replacement, record one EDIT_TIME audit row."""
        reason = self._require_reason(reason)
        original = await self._events.get_by_id(event_id)
        if original is None:
            raise ValidationException("החתמה לא נמצאה")
        if new_time > now:
            raise ValidationException("אי אפשר לקבוע החתמה בעתיד")

        replacement = await self._events.add(
            user_id=original.user_id,
            direction=original.direction,
            punched_at=new_time,
            source=PunchSource.MANUAL,
            note=reason,
            created_by_admin=True,
        )
        adjustment = await self._adjustments.add(
            user_id=original.user_id,
            work_date=original.punched_at.date(),
            action=AdjustmentAction.EDIT_TIME,
            target_event_id=original.id,
            before={
                "punched_at": original.punched_at.isoformat(),
                "direction": original.direction.value,
            },
            after={
                "punched_at": new_time.isoformat(),
                "replacement_event_id": str(replacement.id),
            },
            reason=reason,
        )
        # Recompute both affected days (the time may have crossed midnight).
        await self._pairing.recompute_for_punch(original.user_id, original.punched_at)
        if new_time.date() != original.punched_at.date():
            await self._pairing.recompute_for_punch(original.user_id, new_time)
        return adjustment

    async def add_punch(
        self,
        user_id: uuid.UUID,
        direction: PunchDirection,
        punched_at: datetime,
        reason: str,
        *,
        now: datetime,
    ) -> AttendanceAdjustment:
        """Append a missing punch as a MANUAL event."""
        reason = self._require_reason(reason)
        if punched_at > now:
            raise ValidationException("אי אפשר לקבוע החתמה בעתיד")

        event = await self._events.add(
            user_id=user_id,
            direction=direction,
            punched_at=punched_at,
            source=PunchSource.MANUAL,
            note=reason,
            created_by_admin=True,
        )
        adjustment = await self._adjustments.add(
            user_id=user_id,
            work_date=punched_at.date(),
            action=AdjustmentAction.ADD_PUNCH,
            target_event_id=event.id,
            after={
                "punched_at": punched_at.isoformat(),
                "direction": direction.value,
            },
            reason=reason,
        )
        await self._pairing.recompute_for_punch(user_id, punched_at)
        return adjustment

    async def void_punch(
        self, event_id: uuid.UUID, reason: str
    ) -> AttendanceAdjustment:
        """Logically cancel a wrong punch (the raw row remains for audit)."""
        reason = self._require_reason(reason)
        original = await self._events.get_by_id(event_id)
        if original is None:
            raise ValidationException("החתמה לא נמצאה")

        adjustment = await self._adjustments.add(
            user_id=original.user_id,
            work_date=original.punched_at.date(),
            action=AdjustmentAction.VOID_PUNCH,
            target_event_id=original.id,
            before={
                "punched_at": original.punched_at.isoformat(),
                "direction": original.direction.value,
            },
            reason=reason,
        )
        await self._pairing.recompute_for_punch(original.user_id, original.punched_at)
        return adjustment

    async def mark_absence(
        self, user_id: uuid.UUID, work_date: date_type, reason: str
    ) -> AttendanceAdjustment:
        """Approve a no-show day — its anomaly color clears, tagged ✎."""
        reason = self._require_reason(reason)
        return await self._adjustments.add(
            user_id=user_id,
            work_date=work_date,
            action=AdjustmentAction.MARK_ABSENCE,
            reason=reason,
        )

    async def history(
        self, user_id: uuid.UUID, work_date: date_type
    ) -> list[AttendanceAdjustment]:
        return await self._adjustments.list_for_user_day(user_id, work_date)
