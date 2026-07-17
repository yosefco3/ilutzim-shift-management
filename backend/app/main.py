"""
FastAPI application factory with lifespan, CORS, exception handlers, and health check.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.controllers import (
    auth_router,
    submission_router,
    admin_users_router,
    admin_weeks_router,
    admin_notifications_router,
    admin_export_router,
    admin_settings_router,
    constraints_import_router,
)
from app.schedule_builder.controllers.profile_controller import router as profile_router
from app.schedule_builder.controllers.position_controller import router as position_router
from app.schedule_builder.controllers.attribute_controller import router as attribute_router
from app.schedule_builder.controllers.board_controller import router as board_router
from app.schedule_builder.controllers.assignment_controller import router as assignment_router
from app.schedule_builder.controllers.saved_schedule_controller import router as saved_schedule_router
from app.schedule_builder.controllers.actual_schedule_controller import router as actual_schedule_router
from app.exceptions import (
    AppBaseException,
    app_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL, settings.ENVIRONMENT)
    logger = logging.getLogger("ilutzim")
    logger.info("Application starting", extra={"extra_data": {"environment": settings.ENVIRONMENT}})

    # Fail-fast on weak production secrets (warns only in dev/staging).
    from app.config import validate_production_secrets

    validate_production_secrets(settings, logger)

    # Ensure at least one week exists on startup
    try:
        from app.database import async_session_factory
        from app.seed import ensure_initial_week

        async with async_session_factory() as session:
            await ensure_initial_week(session)
    except Exception as exc:
        logger.warning("Could not ensure initial week: %s", exc)

    # Part B (schedule builder) seed — only when the feature is enabled.
    if settings.SCHEDULE_BUILDER_ENABLED:
        # ensure the default "שגרה" profile exists.
        try:
            from app.database import async_session_factory
            from app.schedule_builder.repositories.profile_repository import ProfileRepository
            from app.schedule_builder.services.profile_service import ProfileService

            async with async_session_factory() as session:
                await ProfileService(ProfileRepository(session)).seed_default_profile()
        except Exception as exc:
            logger.warning("Could not seed default activation profile: %s", exc)

        # ensure the default requirement-attribute vocabulary exists
        # (configurable; editable later from the UI).
        try:
            from app.database import async_session_factory
            from app.schedule_builder.repositories.attribute_repository import AttributeRepository
            from app.schedule_builder.services.attribute_service import AttributeService

            async with async_session_factory() as session:
                await AttributeService(AttributeRepository(session)).seed_default_attributes()
        except Exception as exc:
            logger.warning("Could not seed default requirement attributes: %s", exc)

    # Catch-up rollover: if the Saturday-night transition was missed while the
    # server was down, run it now (idempotent — no-op if already advanced).
    try:
        from app.scheduler import run_weekly_rollover

        await run_weekly_rollover()
    except Exception as exc:
        logger.warning("Startup catch-up rollover failed: %s", exc)

    # Start the weekly rollover scheduler (Sun 00:00 Israel time).
    scheduler = None
    try:
        from app.scheduler import start_scheduler, sync_automation_jobs

        scheduler = start_scheduler()
        if scheduler is not None:
            # Register the auto-open/auto-lock cron jobs from the DB settings.
            await sync_automation_jobs(scheduler)
    except Exception as exc:
        logger.warning("Failed to start rollover scheduler: %s", exc)

    # Start Telegram bot (only if token is configured)
    bot_started = False
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            from app.bot import start_bot

            await start_bot()
            bot_started = True
            logger.info("Telegram bot started")
        except Exception as exc:
            logger.warning("Failed to start Telegram bot: %s", exc)
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set – bot disabled")

    yield

    # Shutdown
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
            logger.info("Rollover scheduler stopped")
        except Exception as exc:
            logger.warning("Error stopping scheduler: %s", exc)

    if bot_started:
        try:
            from app.bot import stop_bot

            await stop_bot()
        except Exception as exc:
            logger.warning("Error stopping bot: %s", exc)

    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Ilutzim App",
        description="Security Guard Shift Management System",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handlers
    app.add_exception_handler(AppBaseException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]

    # Register routers
    app.include_router(auth_router)
    app.include_router(submission_router)
    app.include_router(admin_users_router)
    app.include_router(admin_weeks_router)
    app.include_router(admin_notifications_router)
    app.include_router(admin_export_router)
    app.include_router(admin_settings_router)

    # ── Part B — schedule builder + constraints import (feature-flagged) ──
    # When SCHEDULE_BUILDER_ENABLED is False these routers are not registered,
    # so /admin/builder/* and /admin/import/constraints/* return 404.
    if settings.SCHEDULE_BUILDER_ENABLED:
        app.include_router(constraints_import_router)
        app.include_router(profile_router)
        app.include_router(position_router)
        app.include_router(attribute_router)
        app.include_router(board_router)
        app.include_router(assignment_router)
        app.include_router(saved_schedule_router)
        # The actual-schedule (סידור בפועל) editing API rides the same flag as
        # the rest of the builder half — it is the builder's execution layer.
        # ACTUAL_SCHEDULE_ENABLED governs only the comparison *source*.
        app.include_router(actual_schedule_router)

    # ── Stage 3 — attendance (feature-flagged, ships dormant) ──
    if settings.ATTENDANCE_ENABLED:
        from app.attendance.controllers import attendance_router

        app.include_router(attendance_router)

    # ── Procedure-quiz (סד"פ) — feature-flagged, ships dormant ──
    # When PROCEDURES_ENABLED is False the admin router is not registered (every
    # /admin/procedures/* path returns 404). The bot procedures router and the
    # reminder scheduler job are likewise gated on the flag (see bot_router /
    # scheduler). Nothing new runs until the flag is flipped on.
    if settings.PROCEDURES_ENABLED:
        from app.procedures.controllers import procedures_router

        app.include_router(procedures_router)

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    # ── Serve the built frontend (single-origin production) ──
    # Only when a built `frontend_dist/` is present next to the backend (i.e. in
    # the production Docker image). In local dev the frontend runs on Vite, so
    # this block is skipped and the API stays API-only.
    from pathlib import Path

    dist = Path(__file__).resolve().parent.parent / "frontend_dist"
    if dist.is_dir():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        index_file = dist / "index.html"

        # SPA fallback: any non-API path returns index.html. Registered after all
        # API routers, so /auth, /admin, /submissions, /health match first.
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            return FileResponse(
                index_file,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    return app


app = create_app()