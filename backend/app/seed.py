"""Seed script — creates default admin user and ensures an initial week (idempotent).

Run via: python -m app.seed
All seed values come from config.py (which reads .env).
Override via .env: SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD, SEED_ADMIN_FULL_NAME
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.constants import AdminRole, WeekStatus
from app.database import async_session_factory
from app.models.admin import Admin
from app.models.schedule_week import ScheduleWeek
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.services.auth_service import AuthService, password_strength_errors
from app.utils.date_utils import today_il, week_range

logger = logging.getLogger("ilutzim")


async def seed_admin() -> None:
    """Create the default admin user if it does not already exist."""
    email = settings.SEED_ADMIN_EMAIL
    password = settings.SEED_ADMIN_PASSWORD
    full_name = settings.SEED_ADMIN_FULL_NAME

    pw_errors = password_strength_errors(password)
    if pw_errors:
        msg = "SEED_ADMIN_PASSWORD חלשה: " + "; ".join(pw_errors)
        if settings.ENVIRONMENT != "dev":
            raise RuntimeError(msg + " — קבע סיסמה חזקה ב-env לפני seed בפרודקשן.")
        logger.warning("%s (יחסם מחוץ לסביבת dev)", msg)

    async with async_session_factory() as session:
        result = await session.execute(
            select(Admin).where(Admin.email == email)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  Admin user '{email}' already exists (id={existing.id}). Skipping.")
            return

        admin = Admin(
            email=email,
            password_hash=AuthService.hash_password(password),
            full_name=full_name,
            role=AdminRole.SUPER_ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print(f"  Created admin user '{email}' (id={admin.id}).")


async def ensure_initial_week(session) -> None:
    """Ensure at least one week exists. If DB is empty, create upcoming week as closed.

    A new week always starts CLOSED — the admin opens it manually (which sends
    the open notification to guards).
    """
    repo = ScheduleWeekRepository(session)
    count = await repo.count()
    if count == 0:
        today = today_il()
        start, end = week_range(today)
        week = ScheduleWeek(
            start_date=start,
            end_date=end,
            status=WeekStatus.CLOSED,
        )
        session.add(week)
        await session.commit()
        logger.info(
            "Created initial week %s – %s (closed)",
            start.isoformat(),
            end.isoformat(),
        )
    else:
        logger.debug("Weeks already exist (%d), skipping initial week creation.", count)


if __name__ == "__main__":
    asyncio.run(seed_admin())
