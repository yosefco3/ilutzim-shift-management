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
        """Find an admin by exact email, or by prefix of the local part.

        Allows users to type just 'admin' to match 'admin@example.com'.
        """
        from sqlalchemy import or_

        stmt = select(Admin).where(
            or_(
                Admin.email == username_or_email,
                Admin.email.ilike(f"{username_or_email}%@%"),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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