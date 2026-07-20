"""
Admin repository — data access for dashboard administrators.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AdminRole
from app.models.admin import Admin
from app.repositories.base_repository import BaseRepository
from app.logging_config import get_logger

logger = get_logger(__name__)


class AdminRepository(BaseRepository[Admin]):
    """Data-access for Admin entities (integer PK).

    Inherits the generic CRUD (``get_by_id``/``get_all``/``create``/``update``/
    ``delete``/``save``); the methods below are admin-specific lookups and
    write helpers that the generic layer doesn't cover.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Admin)

    async def get_by_email(self, email: str) -> Admin | None:
        """Find an admin by email address."""
        stmt = select(Admin).where(Admin.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username_or_email(self, username_or_email: str) -> Admin | None:
        """Find an admin by email, or by the local part (before the @).

        Case- and whitespace-insensitive: emails are stored lowercased, so the
        input is stripped and lowercased before matching. This is standard for
        email login — otherwise a stray leading/trailing space or a capital
        letter (browser autofill, mobile auto-capitalization) fails the login
        even with the right password.

        Allows users to type just 'admin' to match 'admin@example.com'. With
        multiple admins a *prefix* match could hit the wrong account (or two
        accounts), so only the full local part matches. If two admins share a
        local part, only an exact-email match is returned — the full email is
        required to disambiguate; ambiguity never raises.
        """
        from sqlalchemy import func, or_

        normalized = username_or_email.strip().lower()
        escaped = (
            normalized.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        email_lower = func.lower(Admin.email)
        stmt = select(Admin).where(
            or_(
                email_lower == normalized,
                email_lower.like(f"{escaped}@%", escape="\\"),
            )
        )
        result = await self.session.execute(stmt)
        admins = list(result.scalars().all())
        if len(admins) == 1:
            return admins[0]
        for admin in admins:
            if admin.email.lower() == normalized:
                return admin
        return None

    async def create_admin(
        self,
        email: str,
        password_hash: str,
        full_name: str,
        role: AdminRole = AdminRole.ADMIN,
    ) -> Admin:
        """Create a new admin user."""
        admin = Admin(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
        )
        self.session.add(admin)
        await self.session.flush()
        logger.debug("Created admin: %s", email)
        return admin

    async def get_all_admins(self) -> list[Admin]:
        """Return all admin records."""
        stmt = select(Admin)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_admin(self, admin_id: int, **kwargs) -> Admin:
        """Update admin fields (name, role, is_active, etc.)."""
        admin = await self.get_by_id(admin_id)
        if admin is None:
            raise ValueError(f"Admin with id={admin_id} not found")
        for key, value in kwargs.items():
            setattr(admin, key, value)
        await self.session.flush()
        await self.session.refresh(admin)
        logger.debug("Updated admin %s", admin_id)
        return admin

    async def deactivate_admin(self, admin_id: int) -> Admin:
        """Set is_active=False on an admin."""
        return await self.update_admin(admin_id, is_active=False)