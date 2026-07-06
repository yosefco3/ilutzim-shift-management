"""
PunchService — the single write path for punches.

Used by the Telegram punch flow now and by the future physical clock / manual
admin entry, so dedup and geofence behavior stay identical across sources.
Never blocks a punch: out-of-radius is recorded and flagged, not rejected
(decision 2026-07-04 — the admin sees, the admin decides).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.attendance.constants import (
    PUNCH_DEDUP_WINDOW_MINUTES,
    PunchDirection,
    PunchSource,
)
from app.attendance.models.attendance_event import AttendanceEvent
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.utils.geo import haversine_m


@dataclass(frozen=True)
class PunchOutcome:
    """Result of a punch attempt.

    ``created=False`` means a same-direction punch already exists inside the
    dedup window — ``event`` is that existing punch (show "already recorded").
    """

    created: bool
    event: AttendanceEvent


class PunchService:
    """Records punches with dedup and geofence classification."""

    def __init__(
        self, events: AttendanceEventRepository, config: AttendanceConfig
    ) -> None:
        self._events = events
        self._config = config

    async def find_recent_duplicate(
        self, user_id: uuid.UUID, direction: PunchDirection, at: datetime
    ) -> AttendanceEvent | None:
        """A same-direction punch inside the dedup window, if one exists.

        Lets the bot answer "already recorded at HH:MM" straight from the
        button tap — without dragging the guard through a location share.
        """
        return await self._events.exists_similar(
            user_id, direction, at, PUNCH_DEDUP_WINDOW_MINUTES
        )

    async def record_punch(
        self,
        user_id: uuid.UUID,
        direction: PunchDirection,
        punched_at: datetime,
        *,
        lat: float | None = None,
        lng: float | None = None,
        accuracy_m: float | None = None,
        source: PunchSource = PunchSource.TELEGRAM,
        note: str | None = None,
        created_by_admin: bool | None = None,
    ) -> PunchOutcome:
        """Append a punch unless it's a double-tap duplicate."""
        duplicate = await self._events.exists_similar(
            user_id, direction, punched_at, PUNCH_DEDUP_WINDOW_MINUTES
        )
        if duplicate is not None:
            return PunchOutcome(created=False, event=duplicate)

        distance = self._distance_from_site(lat, lng)
        event = await self._events.add(
            user_id=user_id,
            direction=direction,
            punched_at=punched_at,
            source=source,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            distance_from_site_m=distance,
            out_of_radius=(
                None if distance is None else distance > self._config.site_radius_m
            ),
            note=note,
            created_by_admin=created_by_admin,
        )
        return PunchOutcome(created=True, event=event)

    def _distance_from_site(self, lat: float | None, lng: float | None) -> float | None:
        """Distance to the configured site; None when either side is unset."""
        if lat is None or lng is None or not self._config.site_configured:
            return None
        return haversine_m(lat, lng, self._config.site_lat, self._config.site_lng)
