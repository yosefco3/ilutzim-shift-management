"""
AdminManagementService — create/deactivate admins and reset their passwords.

All operations are SUPER_ADMIN-only (enforced at the endpoint layer); the
guard rails here protect the system itself: you cannot deactivate yourself or
a super admin, and self password-reset is blocked (the change-password form
verifies the current password — reset would bypass it).
"""

from sqlalchemy.exc import IntegrityError

from app.constants import AdminRole
from app.exceptions import (
    AdminManagementException,
    AdminNotFoundException,
    ConflictException,
    ValidationException,
)
from app.logging_config import get_logger
from app.models.admin import Admin
from app.repositories.admin_repository import AdminRepository
from app.services.auth_service import AuthService, password_strength_errors

logger = get_logger(__name__)

DUPLICATE_EMAIL_MSG = "כתובת המייל כבר קיימת במערכת"


class AdminManagementService:
    """Admin-account management for the SUPER_ADMIN."""

    def __init__(self, admin_repo: AdminRepository) -> None:
        self._admin_repo = admin_repo

    @staticmethod
    def _serialize(admin: Admin) -> dict:
        """Admin as exposed to the UI — never the password hash."""
        return {
            "id": admin.id,
            "email": admin.email,
            "full_name": admin.full_name,
            "role": admin.role.value,
            "is_active": admin.is_active,
            "created_at": admin.created_at,
        }

    async def list_admins(self) -> list[dict]:
        admins = await self._admin_repo.get_all_admins()
        return [self._serialize(a) for a in sorted(admins, key=lambda a: a.id)]

    async def create_admin(self, email: str, full_name: str, password: str) -> dict:
        """Create a new admin. Role is always ADMIN (hierarchy decision)."""
        email = email.strip().lower()

        pw_errors = password_strength_errors(password)
        if pw_errors:
            raise ValidationException("; ".join(pw_errors))

        if await self._admin_repo.get_by_email(email) is not None:
            raise ConflictException(DUPLICATE_EMAIL_MSG)

        try:
            admin = await self._admin_repo.create_admin(
                email=email,
                password_hash=AuthService.hash_password(password),
                full_name=full_name.strip(),
                role=AdminRole.ADMIN,
            )
        except IntegrityError:
            # Concurrent create raced past the check — the unique index fired.
            raise ConflictException(DUPLICATE_EMAIL_MSG)

        logger.info("Admin created: %s (id=%s)", email, admin.id)
        return self._serialize(admin)

    async def set_active(self, caller_id: int, target_id: int, active: bool) -> dict:
        admin = await self._admin_repo.get_by_id(target_id)
        if admin is None:
            raise AdminNotFoundException()

        if not active:
            if target_id == caller_id:
                raise AdminManagementException("אי אפשר להשבית את החשבון שלך")
            if admin.role == AdminRole.SUPER_ADMIN:
                raise AdminManagementException("אי אפשר להשבית חשבון סופר-אדמין")

        updated = await self._admin_repo.update_admin(target_id, is_active=active)
        logger.info("Admin %s: id=%s", "activated" if active else "deactivated", target_id)
        return self._serialize(updated)

    async def reset_password(
        self, caller_id: int, target_id: int, new_password: str
    ) -> None:
        if target_id == caller_id:
            raise AdminManagementException("לשינוי הסיסמה שלך השתמש בטופס שינוי סיסמה")

        admin = await self._admin_repo.get_by_id(target_id)
        if admin is None:
            raise AdminNotFoundException()

        pw_errors = password_strength_errors(new_password)
        if pw_errors:
            raise ValidationException("; ".join(pw_errors))

        await self._admin_repo.update_admin(
            target_id, password_hash=AuthService.hash_password(new_password)
        )
        logger.info("Admin password reset by super admin: id=%s", target_id)
