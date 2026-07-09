"""
Part B — schedule builder dependency providers.

FastAPI ``Depends()`` factories for the schedule-builder services live here
(NOT in ``app/dependencies.py``) to keep the part-A / part-B boundary explicit.
It is fine to import session/auth helpers from part A (dependency rule: B → A).

It is fine to import session/auth helpers from part A (dependency rule: B → A).
"""

from fastapi import Depends

from app.database import get_pool
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.attribute_repository import AttributeRepository
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.repositories.profile_repository import ProfileRepository
from app.schedule_builder.repositories.saved_schedule_repository import (
    SavedScheduleRepository,
)
from app.schedule_builder.repositories.week_profile_repository import (
    WeekProfileRepository,
)
from app.schedule_builder.services.assignment_service import AssignmentService
from app.schedule_builder.services.attribute_service import AttributeService
from app.schedule_builder.services.availability_service import AvailabilityService
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.services.position_service import PositionService
from app.schedule_builder.services.profile_service import ProfileService
from app.schedule_builder.services.saved_schedule_service import (
    SavedScheduleService,
)
from app.schedule_builder.services.week_profile_service import WeekProfileService
from app.services.settings_service import SettingsService


async def get_profile_service(session=Depends(get_pool)) -> ProfileService:
    return ProfileService(
        ProfileRepository(session),
        PositionRepository(session),
        AssignmentRepository(session),
    )


async def get_attribute_service(session=Depends(get_pool)) -> AttributeService:
    return AttributeService(AttributeRepository(session))


async def get_position_service(session=Depends(get_pool)) -> PositionService:
    return PositionService(PositionRepository(session), ProfileRepository(session))


async def get_week_profile_service(session=Depends(get_pool)) -> WeekProfileService:
    return WeekProfileService(
        WeekProfileRepository(session),
        ProfileRepository(session),
        ScheduleWeekRepository(session),
    )


async def get_board_service(session=Depends(get_pool)) -> BoardService:
    return BoardService(
        ScheduleWeekRepository(session),
        WeekProfileService(
            WeekProfileRepository(session),
            ProfileRepository(session),
            ScheduleWeekRepository(session),
        ),
        PositionRepository(session),
    )


async def get_assignment_service(session=Depends(get_pool)) -> AssignmentService:
    return AssignmentService(
        AssignmentRepository(session),
        ScheduleWeekRepository(session),
        PositionRepository(session),
    )


async def get_availability_service(session=Depends(get_pool)) -> AvailabilityService:
    return AvailabilityService(
        ScheduleWeekRepository(session),
        SubmissionRepository(session),
        UserRepository(session),
        AssignmentRepository(session),
        PositionRepository(session),
        settings_service=SettingsService(SystemSettingsRepository(session)),
    )


def build_actual_schedule_service(session) -> "ActualScheduleService":
    """Assemble an ActualScheduleService on a plain session.

    Used by non-request paths (the scheduler's rollover job) as well as the
    Depends() provider below.
    """
    from app.schedule_builder.repositories.actual_schedule_repository import (
        ActualScheduleRepository,
    )
    from app.schedule_builder.services.actual_schedule_service import (
        ActualScheduleService,
    )

    return ActualScheduleService(
        ActualScheduleRepository(session),
        ScheduleWeekRepository(session),
        WeekProfileService(
            WeekProfileRepository(session),
            ProfileRepository(session),
            ScheduleWeekRepository(session),
        ),
        PositionRepository(session),
        AssignmentRepository(session),
        profile_repo=ProfileRepository(session),
    )


async def get_actual_schedule_service(session=Depends(get_pool)):
    return build_actual_schedule_service(session)


def build_actual_schedule_export_service(session):
    """Assemble the actual-schedule read model on a plain session.

    Mirrors ``app.dependencies.get_schedule_export_service`` for the planned
    side; the planned export service is built too, as the future-week fallback.
    """
    from app.repositories.user_repository import UserRepository
    from app.schedule_builder.repositories.actual_schedule_repository import (
        ActualScheduleRepository,
    )
    from app.schedule_builder.services.actual_schedule_export_service import (
        ActualScheduleExportService,
    )
    from app.schedule_builder.services.schedule_export_service import (
        ScheduleExportService,
    )

    week_repo = ScheduleWeekRepository(session)
    planned_export = ScheduleExportService(
        BoardService(
            week_repo,
            WeekProfileService(
                WeekProfileRepository(session),
                ProfileRepository(session),
                ScheduleWeekRepository(session),
            ),
            PositionRepository(session),
        ),
        AssignmentService(
            AssignmentRepository(session),
            ScheduleWeekRepository(session),
            PositionRepository(session),
        ),
        UserRepository(session),
    )
    return ActualScheduleExportService(
        build_actual_schedule_service(session),
        ActualScheduleRepository(session),
        week_repo,
        planned_export,
        UserRepository(session),
    )


async def get_actual_schedule_export_service(session=Depends(get_pool)):
    return build_actual_schedule_export_service(session)


async def get_saved_schedule_service(
    session=Depends(get_pool),
) -> SavedScheduleService:
    return SavedScheduleService(
        SavedScheduleRepository(session),
        BoardService(
            ScheduleWeekRepository(session),
            WeekProfileService(
                WeekProfileRepository(session),
                ProfileRepository(session),
                ScheduleWeekRepository(session),
            ),
            PositionRepository(session),
        ),
        AssignmentRepository(session),
        ScheduleWeekRepository(session),
    )
