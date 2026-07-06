"""
SavedScheduleService — build & persist a frozen schedule snapshot (part B).

``save(week_id)`` reads the *live* board (positions × days, resolved from the
week's effective profile) and the week's assignments, then writes a
**self-contained** snapshot into ``saved_schedules``: position names, guard names,
days, windows and time segments are all copied inline. The snapshot references
**no** profile/position id — that is what lets it survive deletion of the profile
it was built from (deleting a profile cascades positions → assignments, but the
snapshot is untouched).

One snapshot per week: ``save`` upserts. The snapshot reflects the board **at save
time**; later board edits require another save.
"""

import uuid

from app.exceptions import WeekNotFoundException
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models.saved_schedule import SavedSchedule
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.saved_schedule_repository import (
    SavedScheduleRepository,
)
from app.schedule_builder.services.board_service import BoardService


class SavedScheduleService:
    """Snapshot a week's built schedule and read saved snapshots back."""

    def __init__(
        self,
        repo: SavedScheduleRepository,
        board_service: BoardService,
        assignment_repo: AssignmentRepository,
        week_repo: ScheduleWeekRepository,
    ) -> None:
        self._repo = repo
        self._board = board_service
        self._assignment_repo = assignment_repo
        self._week_repo = week_repo

    async def save(self, week_id: uuid.UUID) -> SavedSchedule:
        """Build the snapshot from the live board + assignments and upsert it."""
        week = await self._week_repo.get_by_id(week_id)
        if week is None:
            raise WeekNotFoundException()

        board = await self._board.resolve_board(week_id)
        assignments = await self._assignment_repo.list_for_week(week_id)

        # Index assignments by (position_id, day_index). Each has .user eager-loaded.
        by_cell: dict[tuple, list] = {}
        for a in assignments:
            by_cell.setdefault((a.position_id, a.day_index), []).append(a)

        snapshot = {
            "week": {
                "start_date": week.start_date.isoformat(),
                "end_date": week.end_date.isoformat(),
            },
            "profile_name": board["profile"].name,
            "days": [
                {"index": d["index"], "date": d["date"]} for d in board["days"]
            ],
            "rows": [
                {
                    "position_name": row["name"],
                    "band": row["band"],
                    "canonical_window": row["canonical_window"],
                    "cells": [
                        {
                            "day_index": cell["day_index"],
                            "active": cell["active"],
                            "window": cell["window"],
                            "assignments": [
                                {
                                    "guard_name": a.user.full_name,
                                    "segment_start": a.segment_start,
                                    "segment_end": a.segment_end,
                                }
                                for a in by_cell.get(
                                    (row["position_id"], cell["day_index"]), []
                                )
                            ],
                        }
                        for cell in row["cells"]
                    ],
                }
                for row in board["rows"]
            ],
        }

        return await self._repo.upsert(
            week_id, snapshot["profile_name"], snapshot
        )

    async def get(self, week_id: uuid.UUID) -> SavedSchedule | None:
        """Return the week's saved snapshot, or None if never saved."""
        return await self._repo.get_by_week(week_id)

    async def list_all(self) -> list[SavedSchedule]:
        """Return every saved-schedule row (metadata for the Weeks page)."""
        return await self._repo.list_all()
