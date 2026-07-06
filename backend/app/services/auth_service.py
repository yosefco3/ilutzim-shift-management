"""
AuthService — JWT token creation, password hashing, and admin authentication.
"""

import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import Settings
from app.exceptions import (
    AuthenticationFailedException,
    PasswordChangeException,
    ValidationException,
)
from app.models.admin import Admin
from app.repositories.admin_repository import AdminRepository

logger = logging.getLogger("ilutzim")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Password policy ───────────────────────────────────────────────────────────
PASSWORD_MIN_LENGTH = 10


def password_strength_errors(password: str) -> list[str]:
    """Return a list of policy violations (empty list means the password is OK).

    Pure function — no side effects. Policy: at least 10 characters, with at
    least one letter and one digit. Reused by seeding and the change-password
    endpoint.
    """
    errors: list[str] = []
    if len(password or "") < PASSWORD_MIN_LENGTH:
        errors.append(f"הסיסמה חייבת להכיל לפחות {PASSWORD_MIN_LENGTH} תווים")
    if not any(c.isalpha() for c in (password or "")):
        errors.append("הסיסמה חייבת להכיל לפחות אות אחת")
    if not any(c.isdigit() for c in (password or "")):
        errors.append("הסיסמה חייבת להכיל לפחות ספרה אחת")
    return errors


def validate_password_strength(password: str) -> None:
    """Raise ValidationException if the password violates the policy."""
    errors = password_strength_errors(password)
    if errors:
        raise ValidationException("; ".join(errors))


class AuthService:
    """Handles JWT token creation and admin login verification."""

    def __init__(self, admin_repo: AdminRepository, settings: Settings) -> None:
        self._admin_repo = admin_repo
        self._settings = settings

    async def login_admin(self, username: str, password: str) -> dict:
        """Authenticate admin by username (email or local part) and password.

        Used by the admin dashboard login endpoint.
        Supports login with full email or just the part before '@'.
        """
        admin = await self._admin_repo.get_by_username_or_email(username)
        if admin is None or not admin.is_active:
            logger.warning(f"Admin login failed — not found or inactive: {username}")
            raise AuthenticationFailedException()

        if not pwd_context.verify(password, admin.password_hash):
            logger.warning(f"Admin login failed — bad password: {username}")
            raise AuthenticationFailedException()

        token = self._create_access_token(
            data={"sub": str(admin.id), "role": admin.role.value}
        )
        logger.info(f"Admin authenticated: {username}")
        return {
            "access_token": token,
            "token_type": "bearer",
            "admin_id": admin.id,
            "role": admin.role.value,
        }

    async def change_password(
        self, admin_id: int, current_password: str, new_password: str
    ) -> None:
        """Change a logged-in admin's password.

        Verifies the current password, enforces the password policy, and rejects
        an unchanged password. The admin_id always comes from the caller's token,
        never from the request body.
        """
        admin = await self._admin_repo.get_by_id(admin_id)
        if admin is None or not admin.is_active:
            raise PasswordChangeException("המשתמש לא נמצא או אינו פעיל")

        if not pwd_context.verify(current_password, admin.password_hash):
            logger.warning("Password change failed — wrong current password: id=%s", admin_id)
            raise PasswordChangeException("סיסמה נוכחית שגויה")

        pw_errors = password_strength_errors(new_password)
        if pw_errors:
            raise PasswordChangeException("; ".join(pw_errors))

        if pwd_context.verify(new_password, admin.password_hash):
            raise PasswordChangeException("הסיסמה החדשה זהה לסיסמה הנוכחית")

        await self._admin_repo.update_admin(
            admin_id, password_hash=self.hash_password(new_password)
        )
        logger.info("Admin password changed: id=%s", admin_id)

    def verify_token(self, token: str) -> dict:
        """Decode and validate a JWT token. Returns payload dict."""
        try:
            payload = jwt.decode(
                token,
                self._settings.JWT_SECRET_KEY,
                algorithms=[self._settings.JWT_ALGORITHM],
            )
            return payload
        except JWTError as exc:
            logger.warning(f"JWT verification failed: {exc}")
            raise AuthenticationFailedException()

    def _create_access_token(self, data: dict) -> str:
        """Build a JWT with expiration."""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self._settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
        to_encode["exp"] = expire
        return jwt.encode(
            to_encode,
            self._settings.JWT_SECRET_KEY,
            algorithm=self._settings.JWT_ALGORITHM,
        )

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plaintext password (used for seeding / admin creation)."""
        return pwd_context.hash(password)