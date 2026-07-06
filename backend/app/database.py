"""
Async database engine and session factory.
"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

_engine_kwargs: dict = {
    "echo": settings.ENVIRONMENT == "dev",
}
# pool_size / max_overflow are not valid for SQLite (tests)
if settings.DATABASE_URL.startswith("postgresql"):
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

async_engine = create_async_engine(
    settings.DATABASE_URL,
    **_engine_kwargs,
)

# SQLite (dev/tests) does not enforce foreign keys unless asked. Production runs
# on PostgreSQL where ON DELETE CASCADE works natively; enabling the pragma here
# makes SQLite faithful so cascade-delete (e.g. data-retention purge) behaves the
# same in both.
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(async_engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _record):  # pragma: no cover - infra glue
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_pool() -> AsyncSession:  # type: ignore[misc]
    """Yield an async database session (alias used by dependency injection)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Keep backward-compatible alias
get_db_session = get_pool


class get_session:
    """Synchronous async context manager for bot code (non-FastAPI).

    Usage::

        async with get_session() as session:
            repo = UserRepository(session)
            ...
    """

    def __init__(self):
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self._session = async_session_factory()
        return await self._session.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session is None:
            return False
        try:
            if exc_type is not None:
                await self._session.rollback()
            else:
                await self._session.commit()
        finally:
            await self._session.__aexit__(exc_type, exc_val, exc_tb)
        return False
