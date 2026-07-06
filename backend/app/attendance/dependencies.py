"""
Attendance dependency providers (same boundary role as
``app.schedule_builder.dependencies`` — attendance may import from part A and
consume part B's export service; nothing imports back).
"""

from fastapi import Depends

from app.attendance.repositories.adjustment_repository import (
    AttendanceAdjustmentRepository,
)
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.repositories.shift_repository import AttendanceShiftRepository
from app.attendance.services.adjustment_service import AdjustmentService
from app.attendance.services.attendance_settings import get_attendance_config
from app.attendance.services.comparison_service import ComparisonService
from app.attendance.services.pairing_service import PairingService
from app.config import get_settings
from app.database import get_pool
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.services.settings_service import SettingsService


async def get_event_repo(session=Depends(get_pool)) -> AttendanceEventRepository:
    return AttendanceEventRepository(session)


def _build_comparison_export(session):
    """The schedule source the comparison engine reads from.

    ``ACTUAL_SCHEDULE_ENABLED`` on → the week's editable execution copy
    (סידור בפועל; lazily seeded, future weeks fall back to the plan inside).
    Off → the frozen planning board, exactly the pre-feature behaviour. Both
    return the same ``WeekSchedule``, so the ComparisonService — and payroll /
    alerts / payroll reports downstream — never know which side fed them.
    """
    from app.schedule_builder.repositories.assignment_repository import (
        AssignmentRepository,
    )
    from app.schedule_builder.repositories.position_repository import (
        PositionRepository,
    )
    from app.schedule_builder.repositories.profile_repository import ProfileRepository
    from app.schedule_builder.repositories.week_profile_repository import (
        WeekProfileRepository,
    )
    from app.schedule_builder.services.assignment_service import AssignmentService
    from app.schedule_builder.services.board_service import BoardService
    from app.schedule_builder.services.schedule_export_service import (
        ScheduleExportService,
    )
    from app.schedule_builder.services.week_profile_service import WeekProfileService

    if get_settings().ACTUAL_SCHEDULE_ENABLED:
        from app.schedule_builder.dependencies import (
            build_actual_schedule_export_service,
        )

        return build_actual_schedule_export_service(session)

    week_repo = ScheduleWeekRepository(session)
    board = BoardService(
        week_repo,
        WeekProfileService(
            WeekProfileRepository(session), ProfileRepository(session), week_repo
        ),
        PositionRepository(session),
    )
    return ScheduleExportService(
        board,
        AssignmentService(AssignmentRepository(session), week_repo, PositionRepository(session)),
        UserRepository(session),
    )


async def build_comparison_service(session) -> ComparisonService:
    """Plain (non-Depends) builder — for scheduler jobs that hold their own
    session. Mirrors ``get_comparison_service`` exactly."""
    export = _build_comparison_export(session)
    config = await get_attendance_config(
        SettingsService(SystemSettingsRepository(session))
    )
    return ComparisonService(
        weeks=ScheduleWeekRepository(session),
        users=UserRepository(session),
        shifts=AttendanceShiftRepository(session),
        events=AttendanceEventRepository(session),
        export=export,
        config=config,
        adjustments=AttendanceAdjustmentRepository(session),
    )


async def get_comparison_service(
    session=Depends(get_pool),
) -> ComparisonService:
    return await build_comparison_service(session)


async def get_payroll_readmodel(
    session=Depends(get_pool),
    comparison: ComparisonService = Depends(get_comparison_service),
):
    from app.attendance.services.payroll_readmodel import PayrollReadModel

    return PayrollReadModel(comparison, UserRepository(session), comparison.config)


async def get_adjustment_service(session=Depends(get_pool)) -> AdjustmentService:
    events = AttendanceEventRepository(session)
    return AdjustmentService(
        events=events,
        adjustments=AttendanceAdjustmentRepository(session),
        pairing=PairingService(events, AttendanceShiftRepository(session)),
    )
