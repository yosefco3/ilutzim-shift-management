"""
BoardService — resolves the read-only schedule board (part B, task 04).

Builds the **positions × days** grid for a week from its effective profile. No
guard names and no coverage logic yet (those arrive in 05+). The grid is the
single source of truth for row ordering, so the ordering rules are unit-testable
here rather than in the frontend.

Display bands (derived from each position's *canonical* start time — there is no
"shift" field in the data; the security day runs 07:00 → 07:00):

    🌅 morning  start ∈ [07:00, 15:00)
    🌆 evening  start ∈ [15:00, 23:00)
    🌙 night    start ∈ [23:00, 07:00)   (≥ 23:00 or < 07:00)

Rows group by band (morning→evening→night, derived from the canonical start
time). **Within a band the order is the profile's manual ``display_order``** —
the admin arranges rows by drag-and-drop on the board (a stable sort by band
preserves the display_order the repo already returns). Active-day count is no
longer an ordering rule; it is only the natural default for newly-created
positions, which are appended.
"""

import uuid
from collections import Counter
from datetime import date, timedelta

from app.exceptions import WeekNotFoundException
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models.position import Position
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.services.week_profile_service import WeekProfileService
from app.utils.date_utils import today_il, week_range

# Band cutoffs in minutes-from-midnight (locked with the user, 2026-06-28).
_MORNING_START = 7 * 60   # 07:00
_EVENING_START = 15 * 60  # 15:00
_NIGHT_START = 23 * 60    # 23:00

_BAND_ORDER = {"morning": 0, "evening": 1, "night": 2}


def _to_minutes(hhmm: str) -> int:
    """'HH:MM' -> minutes from midnight."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _band_for(start_min: int) -> str:
    """Map a start time (minutes from midnight) to its display band."""
    if _MORNING_START <= start_min < _EVENING_START:
        return "morning"
    if _EVENING_START <= start_min < _NIGHT_START:
        return "evening"
    return "night"


def _canonical_window(day_schedules: dict) -> dict | None:
    """The most common ``{start, end}`` window across active days (None if empty).

    Days are visited in index order so ties resolve deterministically to the
    earliest day's window.
    """
    if not day_schedules:
        return None
    items = sorted(day_schedules.items(), key=lambda kv: int(kv[0]))
    windows = [(v["start"], v["end"]) for _, v in items]
    start, end = Counter(windows).most_common(1)[0][0]
    return {"start": start, "end": end}


def build_position_row(position) -> dict:
    """Build one board row (a position with its 7 per-day cells).

    Works on anything position-shaped — ``Position`` (planning board) or
    ``ActualPosition`` (the actual-schedule board): both carry ``id`` / ``name``
    / ``day_schedules`` / ``required_attributes`` / ``is_event`` /
    ``event_required_count``. Band and canonical window derive from the hours,
    so the two boards can never disagree on presentation rules.
    """
    day_schedules = position.day_schedules or {}
    canonical = _canonical_window(day_schedules)
    canonical_pair = (
        (canonical["start"], canonical["end"]) if canonical else None
    )
    start_min = _to_minutes(canonical["start"]) if canonical else _NIGHT_START
    band = _band_for(start_min)

    cells = []
    for d in range(7):
        window = day_schedules.get(str(d))
        if window is None:
            cells.append(
                {"day_index": d, "active": False, "window": None, "is_override": False}
            )
            continue
        pair = (window["start"], window["end"])
        cells.append(
            {
                "day_index": d,
                "active": True,
                "window": {"start": window["start"], "end": window["end"]},
                "is_override": canonical_pair is not None and pair != canonical_pair,
            }
        )

    return {
        "position_id": position.id,
        "name": position.name,
        "band": band,
        "canonical_window": canonical,
        "required_attributes": list(position.required_attributes or []),
        "is_event": bool(position.is_event),
        "event_required_count": position.event_required_count,
        "active_day_count": len(day_schedules),
        "cells": cells,
    }


def sort_rows_by_band(rows: list[dict]) -> None:
    """In-place stable sort by band (morning→evening→night).

    Positions arrive ordered by display_order, so within each band the admin's
    manual order is preserved.
    """
    rows.sort(key=lambda r: _BAND_ORDER[r["band"]])


class BoardService:
    """Resolves the read-only board grid for a week."""

    def __init__(
        self,
        week_repo: ScheduleWeekRepository,
        week_profile_service: WeekProfileService,
        position_repo: PositionRepository,
    ) -> None:
        self._week_repo = week_repo
        self._wp_service = week_profile_service
        self._position_repo = position_repo

    async def resolve_board(self, week_id: uuid.UUID) -> dict:
        """Return the resolved board for a specific week id."""
        week = await self._week_repo.get_by_id(week_id)
        if week is None:
            raise WeekNotFoundException()
        return await self._build_board(week)

    async def resolve_next_week_board(self, today: date | None = None) -> dict:
        """Return the board for the **next week** — the same upcoming Sunday→Saturday
        week guards submit availability for (``date_utils.week_range``). The
        schedule is always built for that week, so the board never targets the
        current/in-progress week. Raises ``WeekNotFoundException`` (with a guiding
        message) when the next week has not been created yet.
        """
        start, end = week_range(today or today_il())
        week = await self._week_repo.get_by_date_range(start, end)
        if week is None:
            raise WeekNotFoundException("השבוע הבא טרם נוצר — צור אותו במסך השבועות")
        return await self._build_board(week)

    async def _build_board(self, week) -> dict:
        """Build the resolved board (profile, day columns, ordered rows) for a week."""
        profile, is_default_fallback = await self._wp_service.get_effective_profile(
            week.id
        )
        positions = await self._position_repo.get_by_profile(profile.id)
        rows = [self._build_row(p) for p in positions]
        # Stable sort by band only: positions arrive ordered by display_order,
        # so within each band the admin's manual order (set by drag-and-drop) is
        # preserved. Band is derived from hours, so display_order never crosses a
        # band boundary.
        rows.sort(key=lambda r: _BAND_ORDER[r["band"]])

        days = [
            {"index": i, "date": (week.start_date + timedelta(days=i)).isoformat()}
            for i in range(7)
        ]
        return {
            "week": week,
            "profile": profile,
            "is_default_fallback": is_default_fallback,
            "days": days,
            "rows": rows,
        }

    def _build_row(self, position: Position) -> dict:
        """Build one board row — delegates to the shared row builder."""
        return build_position_row(position)
