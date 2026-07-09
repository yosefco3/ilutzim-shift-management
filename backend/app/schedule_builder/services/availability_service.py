"""
AvailabilityService — the enriched guard pool for a week (part B, task 06).

Builds, for every guard who submitted availability for the week, the data the
schedule builder needs to place them visually:

- ``availability`` — per-day merged windows (HH:MM), derived from the guard's
  ``DailyStatus`` → ``ShiftWindow`` rows. Overlapping shifts are merged (the
  union rule) so the board can colour where the guard can cover.
- ``available_hours`` — the duration of the **union** of those windows across
  the week (not the sum of raw shifts).
- ``assigned_hours`` / ``remaining_hours`` — hours already consumed by this
  guard's current cell assignments (each cell's position window, or its segment)
  and what is left of their weekly availability. The pool is sorted by
  ``remaining_hours`` (most-free first), so the busiest guards sink to the
  bottom. (The optional "AHMASH first" grouping is a client-side toggle in
  ``GuardPool`` — the backend order stays neutral.)
- ``notes`` — the guard's free-text ``general_notes`` from their submission
  (e.g. "עדיפות לבקרים"), surfaced next to their name.

Active guards who did NOT submit for the week can be appended at the end of
the pool (``submitted: False``, empty availability) — controlled by the
``pool_show_unsubmitted`` system setting (default ON) or forced per call via
``include_unsubmitted`` (the warnings endpoint always includes them, so an
assigned non-submitter keeps warning even when the pool switch is OFF).

Coverage colouring per cell is computed client-side from ``availability`` (see
``utils/intervals`` ported to JS) so it updates instantly on selection.
"""

import uuid
from datetime import time

from app.exceptions import WeekNotFoundException
from app.services.automation_settings import as_bool
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.utils import intervals as iv


_ANCHOR = time(7, 0)  # start of the security day


def _hhmm(t) -> str:
    """A ``datetime.time`` → 'HH:MM'."""
    return f"{t.hour:02d}:{t.minute:02d}"


def _clamp_to_anchor(start, end) -> tuple[str, str] | None:
    """A guard's shift window as 'HH:MM' strings, clamped to the security day.

    An early-morning window that starts *before* the 07:00 anchor (e.g. a
    06:30–15:00 morning shift) would, once mapped onto the security-day axis,
    wrap its pre-07:00 sliver to the tail of the day — landing inside the night
    band (23:00–07:00) and making the guard look available for a night shift
    they never submitted. Clamp such a start up to 07:00 so morning availability
    never bleeds into the night. Returns ``None`` when the window lies entirely
    before the anchor (it contributes nothing to this security day).

    Genuine wrapping windows (night shifts like 19:00–07:00 / 23:00–07:00) start
    at or after 07:00 and are left untouched. A window that *both* starts before
    07:00 *and* wraps past midnight (e.g. an import's 05:00–02:00) is also clamped:
    its 05:00–07:00 sliver is a night tail of the *previous* security day and must
    not bleed into this one. Only the constraints **import** can produce
    ``start < 07:00`` — the submission form blocks it via ``_validate_form_window``.
    """
    if start < _ANCHOR:  # window starts before the 07:00 anchor
        wraps = end <= start  # wall-clock end at/before start → crosses midnight
        if not wraps and end <= _ANCHOR:
            return None  # entirely before 07:00 → outside this security day
        # Non-wrapping early morning (06:30–15:00) or wrapping import (05:00–02:00):
        # drop the pre-anchor sliver by clamping the start up to 07:00.
        start = _ANCHOR
    return _hhmm(start), _hhmm(end)


class AvailabilityService:
    """Resolves the enriched, availability-aware guard pool for a week."""

    def __init__(
        self,
        week_repo: ScheduleWeekRepository,
        submission_repo: SubmissionRepository,
        user_repo: UserRepository,
        assignment_repo: AssignmentRepository,
        position_repo: PositionRepository,
        settings_service=None,
    ) -> None:
        self._week_repo = week_repo
        self._submission_repo = submission_repo
        self._user_repo = user_repo
        self._assignment_repo = assignment_repo
        self._position_repo = position_repo
        # Optional (None = the pool_show_unsubmitted default applies) so
        # non-request callers/tests don't have to wire the settings layer.
        self._settings_service = settings_service

    async def build_pool(
        self, week_id: uuid.UUID, include_unsubmitted: bool | None = None
    ) -> list[dict]:
        """Return the enriched pool for a week, sorted by remaining hours desc.

        ``include_unsubmitted``: True/False overrides; None reads the
        ``pool_show_unsubmitted`` setting. When on, active guards without a
        submission are appended after every submitted guard, name-sorted.
        """
        week = await self._week_repo.get_by_id(week_id)
        if week is None:
            raise WeekNotFoundException()

        if include_unsubmitted is None:
            include_unsubmitted = await self._show_unsubmitted()

        submissions = await self._submission_repo.get_submissions_for_week(week_id)
        users = {
            u.id: u
            for u in await self._user_repo.get_by_ids(
                list({s.user_id for s in submissions})
            )
        }
        assigned = await self._assigned_hours_by_user(week_id)

        pool = []
        for sub in submissions:
            user = users.get(sub.user_id)
            if user is None or not user.is_active:
                continue
            availability, available_hours = self._build_availability(sub, week.start_date)
            assigned_hours = assigned.get(user.id, 0.0)
            pool.append({
                "id": user.id,
                "full_name": user.full_name,
                "roles": list(user.roles or []),
                "notes": sub.general_notes,
                "availability": availability,
                "available_hours": available_hours,
                "assigned_hours": assigned_hours,
                "remaining_hours": round(available_hours - assigned_hours, 2),
                "submitted": True,
            })

        pool.sort(key=lambda g: (-g["remaining_hours"], g["full_name"]))
        if include_unsubmitted:
            pool += await self._unsubmitted_entries(week_id, assigned)
        return pool

    async def _show_unsubmitted(self) -> bool:
        """The ``pool_show_unsubmitted`` setting (default ON when unwired)."""
        if self._settings_service is None:
            return True
        return as_bool(
            await self._settings_service.get_setting("pool_show_unsubmitted"),
            default=True,
        )

    async def _unsubmitted_entries(
        self, week_id: uuid.UUID, assigned: dict
    ) -> list[dict]:
        """Pool entries for active guards with no submission, name-sorted.

        Empty availability / zero hours — the warnings engine reads that as
        "no declared coverage", so any placement warns out-of-availability
        (deliberate: assigning them is allowed, with a warning). Their real
        ``assigned_hours`` still count so an already-placed guard shows it.
        """
        active = await self._user_repo.get_active_users()
        missing = set(await self._submission_repo.get_missing_submissions(
            week_id, [u.id for u in active]
        ))
        entries = []
        for user in active:
            if user.id not in missing:
                continue
            assigned_hours = assigned.get(user.id, 0.0)
            entries.append({
                "id": user.id,
                "full_name": user.full_name,
                "roles": list(user.roles or []),
                "notes": None,
                "availability": {},
                "available_hours": 0.0,
                "assigned_hours": assigned_hours,
                "remaining_hours": round(-assigned_hours, 2),
                "submitted": False,
            })
        entries.sort(key=lambda g: g["full_name"])
        return entries

    def _build_availability(self, submission, week_start) -> tuple[dict, float]:
        """Per-day merged windows (HH:MM) + total union hours for a submission."""
        availability: dict[str, list[dict]] = {}
        total_minutes = 0
        for ds in submission.daily_statuses:
            if not ds.is_available or not ds.shift_windows:
                continue
            day_index = (ds.date - week_start).days
            if not 0 <= day_index <= 6:
                continue
            raw = []
            for sw in ds.shift_windows:
                clamped = _clamp_to_anchor(sw.start_time, sw.end_time)
                if clamped is None:
                    continue
                raw += iv.normalize(clamped[0], clamped[1])
            merged = iv.merge(raw)
            if not merged:  # all windows clamped away (entirely pre-anchor)
                continue
            availability[str(day_index)] = [
                {"start": iv.to_hhmm(s), "end": iv.to_hhmm(e)} for s, e in merged
            ]
            total_minutes += sum(e - s for s, e in merged)
        return availability, round(total_minutes / 60, 2)

    async def _assigned_hours_by_user(self, week_id: uuid.UUID) -> dict[uuid.UUID, float]:
        """Sum the consumed window hours per guard from current assignments."""
        assignments = await self._assignment_repo.list_for_week(week_id)
        if not assignments:
            return {}
        positions = {
            p.id: p
            for p in await self._positions_for(
                list({a.position_id for a in assignments})
            )
        }
        out: dict[uuid.UUID, float] = {}
        for a in assignments:
            window = self._assignment_window(a, positions.get(a.position_id))
            if window is None:
                continue
            minutes = iv.duration(iv.normalize(window["start"], window["end"]))
            out[a.user_id] = out.get(a.user_id, 0.0) + minutes / 60
        return {k: round(v, 2) for k, v in out.items()}

    async def _positions_for(self, position_ids: list[uuid.UUID]) -> list:
        """Fetch positions referenced by the assignments (by id)."""
        positions = []
        for pid in position_ids:
            p = await self._position_repo.get_by_id(pid)
            if p is not None:
                positions.append(p)
        return positions

    @staticmethod
    def _assignment_window(assignment, position) -> dict | None:
        """The window an assignment consumes: its segment, else the cell window."""
        if assignment.segment_start and assignment.segment_end:
            return {"start": assignment.segment_start, "end": assignment.segment_end}
        if position is None:
            return None
        return (position.day_schedules or {}).get(str(assignment.day_index))
