"""
FastAPI dependency injection providers.

Provides service instances and authentication guards via Depends().
"""

import logging
import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.constants import AdminRole
from app.database import get_pool
from app.models.user import User
from app.repositories.admin_repository import AdminRepository
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.schedule_builder.dependencies import (
    get_actual_schedule_export_service,
    get_actual_schedule_service,
    get_assignment_service,
    get_board_service,
)
from app.schedule_builder.services.assignment_service import AssignmentService
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.services.schedule_export_service import (
    ScheduleExportService,
)
from app.services.auth_service import AuthService
from app.services.excel_export_service import ExcelExportService
from app.services.settings_service import SettingsService
from app.services.submission_service import SubmissionService
from app.services.user_service import UserService
from app.services.week_service import WeekService
from app.utils.telegram_auth import get_telegram_user_id

logger = logging.getLogger("ilutzim")

_bearer_scheme = HTTPBearer()


# ── Repository providers ─────────────────────────────────────────────────────

async def _get_user_repo(session=Depends(get_pool)) -> UserRepository:
    return UserRepository(session)


async def _get_week_repo(session=Depends(get_pool)) -> ScheduleWeekRepository:
    return ScheduleWeekRepository(session)


async def _get_submission_repo(session=Depends(get_pool)) -> SubmissionRepository:
    return SubmissionRepository(session)


async def _get_admin_repo(session=Depends(get_pool)) -> AdminRepository:
    return AdminRepository(session)


async def _get_settings_repo(session=Depends(get_pool)) -> SystemSettingsRepository:
    return SystemSettingsRepository(session)


# ── Service providers ────────────────────────────────────────────────────────

async def get_auth_service(
    admin_repo: AdminRepository = Depends(_get_admin_repo),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(admin_repo, settings)


async def get_user_service(
    user_repo: UserRepository = Depends(_get_user_repo),
) -> UserService:
    return UserService(user_repo)


async def get_schedule_export_service(
    board_service: BoardService = Depends(get_board_service),
    assignment_service: AssignmentService = Depends(get_assignment_service),
    user_repo: UserRepository = Depends(_get_user_repo),
) -> ScheduleExportService:
    return ScheduleExportService(board_service, assignment_service, user_repo)


async def get_week_service(
    week_repo: ScheduleWeekRepository = Depends(_get_week_repo),
    user_repo: UserRepository = Depends(_get_user_repo),
    schedule_export_service: ScheduleExportService = Depends(
        get_schedule_export_service
    ),
    actual_schedule_service=Depends(get_actual_schedule_service),
) -> WeekService:
    return WeekService(
        week_repo, user_repo, schedule_export_service, actual_schedule_service
    )


async def get_submission_service(
    submission_repo: SubmissionRepository = Depends(_get_submission_repo),
    user_repo: UserRepository = Depends(_get_user_repo),
    week_repo: ScheduleWeekRepository = Depends(_get_week_repo),
) -> SubmissionService:
    return SubmissionService(submission_repo, user_repo, week_repo)


async def get_constraints_commit_service(
    user_repo: UserRepository = Depends(_get_user_repo),
    week_repo: ScheduleWeekRepository = Depends(_get_week_repo),
    submission_service: SubmissionService = Depends(get_submission_service),
) -> "ConstraintsCommitService":
    from app.services.constraints_import.commit import ConstraintsCommitService

    return ConstraintsCommitService(user_repo, week_repo, submission_service)


async def get_settings_service(
    settings_repo: SystemSettingsRepository = Depends(_get_settings_repo),
) -> SettingsService:
    return SettingsService(settings_repo)


async def get_excel_export_service(
    submission_repo: SubmissionRepository = Depends(_get_submission_repo),
    user_repo: UserRepository = Depends(_get_user_repo),
    week_repo: ScheduleWeekRepository = Depends(_get_week_repo),
    schedule_export_service: ScheduleExportService = Depends(
        get_schedule_export_service
    ),
    actual_export_service=Depends(get_actual_schedule_export_service),
) -> ExcelExportService:
    return ExcelExportService(
        submission_repo, user_repo, week_repo, schedule_export_service,
        actual_export_service,
    )


# ── Auth guards ──────────────────────────────────────────────────────────────

async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """
    Validate Bearer token and return the decoded payload.
    Raises 401 if token is invalid.
    """
    try:
        payload = auth_service.verify_token(credentials.credentials)
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin_role(
    admin: dict = Depends(get_current_admin),
) -> dict:
    """Require admin or super_admin role."""
    role = admin.get("role")
    if role not in (AdminRole.ADMIN, AdminRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return admin


async def get_current_user(
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
    settings: Settings = Depends(get_settings),
    user_repo: UserRepository = Depends(_get_user_repo),
    settings_service: SettingsService = Depends(get_settings_service),
) -> User:
    """Authenticate a guard via Telegram WebApp init data header.

    Returns the User model or raises 401.
    The '__DEV_MODE__' bypass returns the first active user, but ONLY when
    BOTH DEV_AUTH_BYPASS_ENABLED is set AND ENVIRONMENT == 'dev'. In any other
    case the literal is treated as invalid Telegram data and rejected (no auth
    bypass in production, and never without the explicit opt-in flag).
    """
    if (
        x_telegram_init_data == "__DEV_MODE__"
        and settings.DEV_AUTH_BYPASS_ENABLED
        and settings.ENVIRONMENT == "dev"
    ):
        users = await user_repo.get_active_users()
        if not users:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No active users found (dev mode)",
            )
        return users[0]

    bot_token = await settings_service.get_effective_bot_token()
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bot token not configured",
        )

    telegram_id = get_telegram_user_id(x_telegram_init_data, bot_token)
    if telegram_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram data",
        )

    user = await user_repo.get_by_telegram_id(telegram_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guard not found",
        )

    return user
