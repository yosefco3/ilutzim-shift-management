"""
Custom exception classes and global FastAPI exception handlers.
"""

import logging
import traceback

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.messages import Messages

logger = logging.getLogger("ilutzim")


# ── Base exception ────────────────────────────────────────────────────


class AppBaseException(Exception):
    """Base exception for all application-specific errors."""

    status_code: int = 500
    message: str = "שגיאה פנימית"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


# ── Concrete exceptions ───────────────────────────────────────────────


class WeekLockedException(AppBaseException):
    status_code = 403
    message = Messages.ERR_WEEK_LOCKED


class UserNotAuthorizedException(AppBaseException):
    status_code = 401
    message = Messages.ERR_AUTH_FAILED


class UserDeactivatedException(AppBaseException):
    status_code = 403
    message = Messages.ERR_USER_DEACTIVATED


class UserNotFoundException(AppBaseException):
    status_code = 404
    message = Messages.ERR_USER_NOT_FOUND


class ValidationException(AppBaseException):
    status_code = 422
    message = Messages.ERR_VALIDATION


class ConflictException(AppBaseException):
    status_code = 409
    message = Messages.ERR_CONFLICT


class InvalidTransitionException(AppBaseException):
    """Raised when a week status transition is not allowed."""
    status_code = 400


class AdminNotFoundException(AppBaseException):
    status_code = 404
    message = Messages.ERR_USER_NOT_FOUND


class AuthenticationFailedException(AppBaseException):
    """Raised when Telegram authentication fails."""
    status_code = 401


class InvalidCredentialsException(AppBaseException):
    status_code = 401
    message = Messages.ERR_AUTH_FAILED


class TokenExpiredException(AppBaseException):
    status_code = 401
    message = Messages.ERR_AUTH_FAILED


class InsufficientPermissionsException(AppBaseException):
    status_code = 403
    message = Messages.ERR_AUTH_FAILED


class PasswordChangeException(AppBaseException):
    """Raised when an admin password change is rejected (wrong current password,
    weak new password, or unchanged password)."""
    status_code = 400
    message = "שינוי סיסמה נכשל"


# ── Part B — schedule builder ─────────────────────────────────────────

class ProfileNotFoundException(AppBaseException):
    """Raised when an activation profile does not exist."""
    status_code = 404
    message = "פרופיל לא נמצא"


class ProfileDeleteBlockedException(AppBaseException):
    """Raised when deleting a profile would leave no profiles, or remove the
    sole default profile."""
    status_code = 409
    message = "לא ניתן למחוק את הפרופיל האחרון שנותר"


class AttributeNotFoundException(AppBaseException):
    """Raised when a requirement attribute does not exist."""
    status_code = 404
    message = "מאפיין לא נמצא"


class AttributeKeyConflictException(AppBaseException):
    """Raised when creating an attribute whose key already exists."""
    status_code = 409
    message = "מפתח מאפיין כבר קיים"


class PositionNotFoundException(AppBaseException):
    """Raised when a position does not exist."""
    status_code = 404
    message = "עמדה לא נמצאה"


class PositionReorderMismatchException(AppBaseException):
    """Raised when a reorder body is not an exact permutation of the profile's
    positions (a missing, foreign, or extra id)."""
    status_code = 400
    message = "רשימת הסדר חייבת להכיל בדיוק את עמדות הפרופיל"


class WeekNotFoundException(AppBaseException):
    """Raised when a schedule week does not exist."""
    status_code = 404
    message = "שבוע לא נמצא"


class AssignmentNotFoundException(AppBaseException):
    """Raised when a schedule assignment does not exist."""
    status_code = 404
    message = "שיבוץ לא נמצא"


class CellInactiveException(AppBaseException):
    """Raised when assigning a guard to a day the position is not active on."""
    status_code = 422
    message = "העמדה אינה פעילה ביום זה"


class GuardAlreadyAssignedException(AppBaseException):
    """Raised when the same guard is already assigned in the cell."""
    status_code = 409
    message = "המאבטח כבר משובץ בתא זה"


class CellFullException(AppBaseException):
    """A cell holds up to two guards (time-tiling); a third is blocked."""
    status_code = 409
    message = "התא מלא — אפשר עד שני מאבטחים במשבצת"


class WeekNotEditableException(AppBaseException):
    """The board is frozen: the week has already started (start_date <= today).

    Board-building happens while the week is still upcoming. Once it starts (the
    Sunday rollover → LOCKED), the schedule is frozen — no assignments may be
    added, moved or removed. A published-but-not-yet-started week stays CLOSED and
    editable/re-publishable, so the gate keys on the date, not the status."""
    status_code = 409
    message = "לא ניתן לערוך לוח לשבוע שכבר התחיל"


# ── Global exception handlers ─────────────────────────────────────────


async def app_exception_handler(request: Request, exc: AppBaseException) -> JSONResponse:
    """Handle all AppBaseException subclasses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "detail": None},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic RequestValidationError."""
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": Messages.ERR_VALIDATION,
            "detail": exc.errors(),
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler — logs traceback and returns 500."""
    logger.error(f"Unhandled exception: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "שגיאה פנימית בשרת", "detail": None},
    )