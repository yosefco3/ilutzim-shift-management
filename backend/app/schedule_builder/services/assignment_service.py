"""
AssignmentService — manual schedule assignment (part B, task 05).

Fills board cells: place a guard on a position×day for a week, or remove the
placement. The model supports tiling (several guards per cell, each with an
optional time segment); the current UI assigns one guard per cell.

Validation is deliberately light — by design (locked with the user, 2026-06-29):
assigning a guard who lacks a position's *required attribute* is **allowed** (the
soft warning arrives in task 07). We only guard structural integrity: the week
and position must exist, the position must be active on that day, and the same
guard may not be placed in the same cell twice.
"""

import uuid

from app.exceptions import (
    AssignmentNotFoundException,
    CellFullException,
    CellInactiveException,
    GuardAlreadyAssignedException,
    PositionNotFoundException,
    WeekNotEditableException,
    WeekNotFoundException,
)
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.utils.date_utils import today_il
from app.schedule_builder.models.schedule_assignment import ScheduleAssignment
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository


class AssignmentService:
    """Create, list and remove manual cell assignments for a week."""

    def __init__(
        self,
        assignment_repo: AssignmentRepository,
        week_repo: ScheduleWeekRepository,
        position_repo: PositionRepository,
    ) -> None:
        self._repo = assignment_repo
        self._week_repo = week_repo
        self._position_repo = position_repo

    async def list_for_week(self, week_id: uuid.UUID) -> list[ScheduleAssignment]:
        """Return every assignment for a week (raises if the week is unknown)."""
        if await self._week_repo.get_by_id(week_id) is None:
            raise WeekNotFoundException()
        return await self._repo.list_for_week(week_id)

    async def _require_editable_week(self, week_id: uuid.UUID):
        """Load the week and assert its board is still editable.

        The board is built while the week is upcoming; once it has started
        (``start_date <= today_il()`` — the Sunday rollover) it is frozen, whatever
        its status. A CLOSED week that was already published is NOT frozen — publish
        keeps it CLOSED, so the admin can still edit and re-publish it until it
        starts. Returns the week for callers that need it."""
        week = await self._week_repo.get_by_id(week_id)
        if week is None:
            raise WeekNotFoundException()
        if week.start_date <= today_il():
            raise WeekNotEditableException()
        return week

    async def assign(
        self,
        week_id: uuid.UUID,
        position_id: uuid.UUID,
        day_index: int,
        user_id: uuid.UUID,
        segment_start: str | None = None,
        segment_end: str | None = None,
    ) -> ScheduleAssignment:
        """Place a guard on a cell. Segment is optional (null = whole window)."""
        await self._require_editable_week(week_id)

        position = await self._position_repo.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundException()

        # The cell must be a real, active cell of the position that day.
        if str(day_index) not in (position.day_schedules or {}):
            raise CellInactiveException()

        # Hard cap on how many guards a cell holds:
        #   - normal position: 2 (time-tiling). A third is the one place the
        #     otherwise-soft builder blocks — three-in-a-tile is an invalid state.
        #   - event with a fixed participant count: that count (e.g. מועצה = 4);
        #     the cell tiles into that many slots.
        #   - event without a count (רענון): unlimited — no cap.
        if not position.is_event:
            cap = 2
        elif position.event_required_count is not None:
            cap = position.event_required_count
        else:
            cap = None
        if cap is not None:
            in_cell = await self._repo.list_in_cell(week_id, position_id, day_index)
            if len(in_cell) >= cap:
                raise CellFullException()

        existing = await self._repo.get_in_cell(
            week_id, position_id, day_index, user_id
        )
        if existing is not None:
            raise GuardAlreadyAssignedException()

        created = await self._repo.create(
            week_id=week_id,
            position_id=position_id,
            day_index=day_index,
            user_id=user_id,
            segment_start=segment_start,
            segment_end=segment_end,
        )
        # Re-fetch with the guard eager-loaded so the response carries name/roles.
        return await self._repo.get_with_user(created.id)

    async def update_segment(
        self,
        assignment_id: uuid.UUID,
        segment_start: str | None,
        segment_end: str | None,
    ) -> ScheduleAssignment:
        """Set/clear an assignment's time segment (the draggable-divider save)."""
        assignment = await self._repo.get_with_user(assignment_id)
        if assignment is None:
            raise AssignmentNotFoundException()
        await self._require_editable_week(assignment.week_id)
        updated = await self._repo.update_segment(
            assignment_id, segment_start, segment_end
        )
        if updated is None:
            raise AssignmentNotFoundException()
        return updated

    async def unassign(self, assignment_id: uuid.UUID) -> bool:
        """Remove an assignment by id. Returns False if it did not exist."""
        assignment = await self._repo.get_with_user(assignment_id)
        if assignment is None:
            return False
        await self._require_editable_week(assignment.week_id)
        return await self._repo.delete(assignment_id)
