"""
ActualScheduleExportService — the actual-schedule read model (step 03).

The exact counterpart of :class:`ScheduleExportService`, reading from the
week's editable execution copy (``actual_*`` tables) instead of the planning
board — and returning the very same :class:`WeekSchedule` through the very same
source-agnostic core (``build_week_schedule``). Any consumer of the planned
read model (the attendance comparison, the Excel grid) can be re-pointed here
by swapping the injected service, nothing else.

Two behaviours specific to this side:

- **Lazy seeding** — reading a week that has no copy yet seeds it on the spot
  (idempotent ``ensure_for_week``), so weeks that predate the feature and
  missed rollovers heal transparently on first access.
- **Future weeks delegate to the plan** — until a week starts, the plan *is*
  the expected execution, and the actual layer does not exist yet. A month view
  spanning next week keeps working without special-casing callers.
"""

import logging
import uuid
from datetime import timedelta

from app.schedule_builder.services.actual_schedule_service import (
    ActualScheduleNotAvailableException,
    ActualScheduleService,
)
from app.schedule_builder.services.board_service import (
    build_position_row,
    sort_rows_by_band,
)
from app.schedule_builder.services.schedule_export_service import (
    ScheduleExportService,
    WeekSchedule,
    build_week_schedule,
)

logger = logging.getLogger("ilutzim")


class ActualScheduleExportService:
    """Resolve a week's *actual* schedule into the shared read model."""

    def __init__(
        self,
        actual_service: ActualScheduleService,
        actual_repo,
        week_repo,
        planned_export: ScheduleExportService,
        user_repo,
    ) -> None:
        self._actual = actual_service
        self._repo = actual_repo
        self._week_repo = week_repo
        self._planned_export = planned_export
        self._user_repo = user_repo

    async def get_week_schedule(self, week_id: uuid.UUID) -> WeekSchedule:
        """Build both cuts from the actual layer (seeding lazily if needed).

        Raises ``WeekNotFoundException`` for unknown weeks. A week that has not
        started yet falls back to the planned read model.
        """
        try:
            actual = await self._actual.ensure_for_week(week_id)
        except ActualScheduleNotAvailableException:
            return await self._planned_export.get_week_schedule(week_id)

        week = await self._week_repo.get_by_id(week_id)
        positions = await self._repo.list_positions(actual.id)
        assignments = await self._repo.list_assignments(actual.id)
        guards = await self._user_repo.get_active_users()

        rows = [build_position_row(p) for p in positions]
        sort_rows_by_band(rows)
        days = [
            {"index": i, "date": (week.start_date + timedelta(days=i)).isoformat()}
            for i in range(7)
        ]
        return build_week_schedule(week, days, rows, assignments, guards)
