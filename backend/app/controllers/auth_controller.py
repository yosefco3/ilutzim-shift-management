"""
AuthController — Telegram WebApp login and admin panel login.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_auth_service, get_current_admin
from app.schemas.user_schemas import ChangePasswordRequest, LoginRequest
from app.services.auth_service import AuthService
from app.services.login_throttle import get_login_throttle

logger = logging.getLogger("ilutzim")

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/admin/login")
async def admin_login(
    body: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate an admin via username/password.

    Returns JWT with admin claims if credentials are valid.
    """
    if not body.username or not body.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required",
        )

    throttle = get_login_throttle()
    # Same message whether or not the identity exists — do not leak account
    # existence via the lockout response.
    if throttle.is_locked(body.username):
        minutes = throttle.minutes_until_unlock(body.username)
        logger.warning("Admin login blocked (locked): %s", body.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"יותר מדי נסיונות התחברות. נסה שוב בעוד {minutes} דקות.",
        )

    try:
        result = await auth_service.login_admin(body.username, body.password)
    except Exception as e:
        throttle.record_failure(body.username)
        logger.warning("Admin login failed for '%s': %s", body.username, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    throttle.reset(body.username)
    return result


@router.post("/admin/change-password")
async def admin_change_password(
    body: ChangePasswordRequest,
    admin: dict = Depends(get_current_admin),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Change the logged-in admin's own password.

    The admin id is taken from the JWT (`sub`), never from the body, so an admin
    can only change their own password. Requires the current password.
    """
    admin_id = int(admin.get("sub"))
    await auth_service.change_password(
        admin_id, body.current_password, body.new_password
    )
    return {"success": True}


@router.get("/me")
async def get_me(admin: dict = Depends(get_current_admin)):
    """Return current admin info from JWT."""
    return {
        "id": admin.get("sub"),
        "username": admin.get("username"),
        "role": admin.get("role"),
    }