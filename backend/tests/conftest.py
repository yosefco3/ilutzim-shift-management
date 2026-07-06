"""
Shared test fixtures.
"""

import os
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set test environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("APP_URL", "http://localhost:3000")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("DEV_AUTH_BYPASS_ENABLED", "true")

from datetime import date, timedelta

from app.constants import WeekStatus
from app.main import create_app
from app.models import Base  # noqa: F401  — ensures all models are registered
from app.models.schedule_week import ScheduleWeek
import app.models  # noqa: F401  — import all model modules


# ---------- HTTP client fixture ----------

@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Provide an async HTTP test client."""
    application = create_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------- In-memory SQLite DB for model tests ----------

TEST_DB_URL = "sqlite+aiosqlite://"
test_engine = create_async_engine(TEST_DB_URL, echo=False)


@event.listens_for(test_engine.sync_engine, "connect")
def _enable_test_sqlite_fk(dbapi_conn, _record):
    """Enforce FK constraints (incl. ON DELETE CASCADE) so tests mirror prod."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=False)
async def db_session():
    """Yield a clean DB session with all tables created (in-memory SQLite)."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def sample_week(db_session):
    """Create a sample week in LOCKED status for testing."""
    from app.utils.date_utils import week_range
    start, end = week_range(date.today())
    week = ScheduleWeek(
        start_date=start,
        end_date=end,
        status=WeekStatus.LOCKED,
    )
    db_session.add(week)
    await db_session.commit()
    await db_session.refresh(week)
    return week
